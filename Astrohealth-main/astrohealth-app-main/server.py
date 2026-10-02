import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from flask import (Flask, request,
                   jsonify, send_from_directory, g)
from flask_cors import CORS
from timezonefinder import TimezoneFinder
from datetime import datetime
import pytz
import httpx
import asyncio
import time
import json as _json

import os

from werkzeug.exceptions import HTTPException
from app_core.errors import AuthorizationError, RequestValidationError, UpstreamError
from app_core.http import enforce_patient_access, register_http, require_auth, safe_failure
from app_core.logging_config import log
from app_core.prokerala_token import get_prokerala_token
from app_core.runtime import get_services
from app_core.validation import parse_chart_input, parse_chat_message, require_session_id

app = Flask(__name__)
_settings = get_services().settings
CORS(
    app,
    resources={r"/*": {"origins": _settings.allowed_origins}},
    supports_credentials=False,
)
register_http(app)
    
from rules import (
    apply_rule_1,
    generate_chat_questions,
    analyse_dasha,
    complete_risk_analysis
)

from jataka_fetch import fetch_and_save
from jataka_logic import run_logic
from disease_diagnose import run_diagnose
from chat_module import (
    start_chat as chat_start,
    send_message as chat_send_message
)
from combine_output import run_combine
from imp_rashi_distance import (
    build_imp_rashi_distance_analysis,
    build_birth_current_distance_analysis,
)
from second_ascendant import calculate_second_ascendant
from knowledge_base import (
    NAKSHATRA_DISEASES,
    PLANET_DISEASES,
    RASHI_ORGANS,
    NAKSHATRA_LORDS,
    filter_nakshatra_diseases_by_gender,
    filter_planet_diseases_by_gender,
    filter_rashi_organs_by_gender,
    filter_terms_by_gender,
    get_nakshatra_diseases,
    normalize_gender,
)
from zone_engine import run_zone_analysis
from chart_specific_overrides import apply_bhadravathi_overrides, apply_person2_overrides
from algorithm_comparison_v2 import build_combined_algo_summary_v2
from priority_cascade import build_full_cascade_view, build_cascade_tiers, build_drishti_catalysts, build_ascendant_reference, build_house_occupant_reference
from disease_priority_cascade_logic import run_disease_priority_cascade_logic
from disease_priority_cascade_logic_v2 import run_disease_priority_cascade_logic_v2, build_organ_priority_view
from shadbala_weighted_disease_priority import run_shadbala_weighted_disease_priority
from dasha_weighted_disease_priority import run_dasha_weighted_disease_priority



def _json_fallback_message(message: str, question_type: str = "context") -> str:
    return _json.dumps({
        "reasoning": "System fallback response due to temporary model/API issue.",
        "cluster_rank": 0,
        "question_type": question_type,
        "chat_message": message
    })

'''app = Flask(__name__)
CORS(app)'''

from config import (
    PROKERALA_CLIENT_ID,
    PROKERALA_CLIENT_SECRET,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    LLM_PROVIDER
)

# In-memory conversation store
# session_id -> conversation data
conversation_store = {}

# Credentials now imported from config.py

async def get_token() -> str:
    return await get_prokerala_token(PROKERALA_CLIENT_ID, PROKERALA_CLIENT_SECRET)


def get_timezone_offset(lat: float, lng: float) -> str:
    """Returns UTC offset string e.g. '+05:30' for a given lat/lng."""
    try:
        tf      = TimezoneFinder()
        tz_name = tf.timezone_at(lat=lat, lng=lng)
        if not tz_name:
            return "+05:30"
        tz     = pytz.timezone(tz_name)
        offset = datetime.now(tz).strftime("%z")   # "+0530"
        return f"{offset[:3]}:{offset[3:]}"        # "+05:30"
    except Exception:
        return "+05:30"


def get_timezone_name(lat: float, lng: float) -> str:
    try:
        tf = TimezoneFinder()
        return tf.timezone_at(lat=lat, lng=lng) or "Asia/Kolkata"
    except Exception:
        return "Asia/Kolkata"


def build_planet_position_snapshot(data: dict) -> dict:
    """Parse Prokerala planet-position payload into UI-friendly planet rows."""
    NAKSHATRAS = [
        "Ashwini","Bharani","Krithika","Rohini",
        "Mrigashira","Aridra","Punarvasu","Pushya",
        "Ashlesha","Magha","Purvaphalguni",
        "Uttara Phalguni","Hasta","Chitha","Swathi",
        "Vishaka","Anuradha","Jyesta","Moola",
        "Poorvashada","Uttaraashada","Shravana",
        "Dhanishta","Shathabhisha","Poorvabhadra",
        "Uttara Bhadrapada","Revathi"
    ]
    ZODIAC_IDX = {
        "Mesha": 0, "Vrishabha": 1, "Mithuna": 2, "Karka": 3,
        "Simha": 4, "Kanya": 5, "Tula": 6, "Vrischika": 7,
        "Dhanu": 8, "Makara": 9, "Kumbha": 10, "Meena": 11
    }

    def calc_nakshatra(sign_name, deg, mins):
        sign_idx = ZODIAC_IDX.get(sign_name, 0)
        full_lon = sign_idx * 30 + deg + mins / 60.0
        nk_idx = int(full_lon / 13.3333) % 27
        pada = int((full_lon % 13.3333) / 3.3333) + 1
        return {"name": NAKSHATRAS[nk_idx], "pada": min(pada, 4)}

    nakshatra_map = {}
    for p in data.get("planet_position", []):
        pname = p.get("name", "")
        sign_name = p.get("rasi", {}).get("name", "Mesha")
        deg_raw = p.get("degree", 0)
        deg = int(deg_raw)
        mins = int((deg_raw % 1) * 60)
        nakshatra_map[pname] = calc_nakshatra(sign_name, deg, mins)

    ascendant = {}
    for p in data.get("planet_position", []):
        if p.get("name") == "Ascendant":
            asc_id = p.get("rasi", {}).get("id", 0)
            ascendant = {
                "name": p.get("rasi", {}).get("name", "—"),
                "id": asc_id,
                "house": 1,
                "nakshatra": nakshatra_map.get("Ascendant", {"name": "—", "pada": ""}),
            }
            break

    asc_position = ascendant["id"] + 1 if "id" in ascendant else 1
    planets = []
    for p in data.get("planet_position", []):
        pname = p.get("name", "")
        if pname == "Ascendant":
            planets.append({
                "name": "Ascendant",
                "house": 1,
                "absolute_house": p.get("position", 1),
                "sign": {"name": p.get("rasi", {}).get("name", "—")},
                "degree": int(p.get("degree", 0)),
                "minutes": int((p.get("degree", 0) % 1) * 60),
                "nakshatra": nakshatra_map.get("Ascendant", {"name": "—", "pada": ""}),
                "isRetrograde": False,
            })
            continue

        planet_position = p.get("position", 1)
        house_number = ((planet_position - asc_position) % 12) + 1
        planets.append({
            "name": pname,
            "house": house_number,
            "absolute_house": planet_position,
            "sign": {"name": p.get("rasi", {}).get("name", "—")},
            "degree": int(p.get("degree", 0)),
            "minutes": int((p.get("degree", 0) % 1) * 60),
            "nakshatra": nakshatra_map.get(pname, {"name": "—", "pada": ""}),
            "isRetrograde": p.get("is_retrograde", False),
        })
    return {"ascendant": ascendant, "planets": planets}


def _legacy_build_imp_rashi_distance_analysis_unused(chart_data: dict, rule1_result: dict, current_positions: dict, dasha_result: dict) -> dict:
    planets = chart_data.get("planets", []) or []
    houses = chart_data.get("houses", []) or []
    current_planets = (current_positions or {}).get("planets", []) or []
    current_by_name = {p.get("name"): p for p in current_planets if p.get("name")}

    moon = next((p for p in planets if p.get("name") == "Moon"), None)
    if not moon:
        return {
            "available": False,
            "reason": "Moon not found in birth chart planets.",
            "rows": [],
            "trail": {"error": "Moon not found"},
        }

    imp_house = int(moon.get("house", 0) or 0)
    imp_rashi = ""
    for house in houses:
        if int(house.get("house", 0) or 0) == imp_house:
            imp_rashi = ((house.get("sign") or {}).get("name", ""))
            break

    active_dasha = {
        "mahadasha": ((dasha_result or {}).get("mahadasha") or {}).get("planet", "—"),
        "antardasha": ((dasha_result or {}).get("antardasha") or {}).get("planet", "—"),
        "pratyantardasha": ((dasha_result or {}).get("pratyantardasha") or {}).get("planet", "—"),
    }

    increase_set = {2, 6, 7, 8, 12}
    lower_set = {1, 3, 4, 5, 9, 10, 11}

    role_rows = []

    def add_role_rows(role_code: str, role_label: str, items):
        if not items:
            return
        iterable = items if isinstance(items, list) else [items]
        for index, item in enumerate(iterable, start=1):
            if not item:
                continue
            planet_name = item.get("name") if isinstance(item, dict) else ""
            if not planet_name:
                continue
            current_planet = current_by_name.get(planet_name) or {}
            current_abs_house = int(current_planet.get("absolute_house", 0) or 0)
            current_sign = ((current_planet.get("sign") or {}).get("name", "—"))

            raw_gap = ((current_abs_house - imp_house + 12) % 12) if imp_house and current_abs_house else None
            distance = (raw_gap + 1) if raw_gap is not None else None

            active_levels = []
            if planet_name == active_dasha["mahadasha"]:
                active_levels.append("Mahadasha")
            if planet_name == active_dasha["antardasha"]:
                active_levels.append("Antardasha")
            if planet_name == active_dasha["pratyantardasha"]:
                active_levels.append("Pratyantardasha")

            bucket = "unmapped"
            effect = "No rule"
            if distance in increase_set:
                bucket = "increase"
                effect = "Increase Severity" if active_levels else "Increase Pattern Present"
            elif distance in lower_set:
                bucket = "lower"
                effect = "Lower / Nullify" if active_levels else "Lower / Nullify Pattern"

            role_rows.append({
                "role": role_code if len(iterable) == 1 else f"{role_code}.{index}",
                "role_base": role_code,
                "role_label": role_label,
                "moon_house": imp_house,
                "planet": planet_name,
                "birth_reference_sign": imp_rashi or "—",
                "current_absolute_house": current_abs_house or None,
                "current_sign": current_sign or "—",
                "raw_gap": raw_gap,
                "distance": distance,
                "distance_bucket": bucket,
                "dasha_active_levels": active_levels,
                "effect": effect,
                "note": (
                    f"Distance {distance} is in the {'increase' if bucket == 'increase' else 'lower/nullify' if bucket == 'lower' else 'unmapped'} group."
                    + (f" Active dasha: {', '.join(active_levels)}." if active_levels else " Planet is not active in current dasha.")
                ) if distance is not None else "Current planetary position not found for this planet.",
                "backend_trail": {
                    "imp_house": imp_house,
                    "target_absolute_house": current_abs_house or None,
                    "raw_gap_formula": f"(({current_abs_house} - {imp_house} + 12) % 12) = {raw_gap}" if current_abs_house else "Target house unavailable",
                    "distance_formula": f"{raw_gap} + 1 = {distance}" if raw_gap is not None else "Distance unavailable",
                    "increase_set": sorted(increase_set),
                    "lower_set": sorted(lower_set),
                    "active_dasha_levels": active_levels,
                }
            })

    add_role_rows("P1", "Occupant", rule1_result.get("rogkaraka_1", []))
    add_role_rows("P2", "Dispositor", rule1_result.get("rogkaraka_3"))
    add_role_rows("P3", "Drishti", [{"name": row.get("planet", "")} for row in (rule1_result.get("drishti_on_6th", []) or []) if row.get("planet")])
    add_role_rows("P4", "6th House Lord", rule1_result.get("rogkaraka_2"))

    return {
        "available": True,
        "title": "IMP Rashi Distance",
        "imp_rashi": {
            "moon_house": imp_house,
            "sign": imp_rashi or "—",
            "moon_sign": ((moon.get("sign") or {}).get("name", "—")) if isinstance(moon.get("sign"), dict) else moon.get("sign", "—"),
        },
        "rules": {
            "increase_distances": sorted(increase_set),
            "lower_distances": sorted(lower_set),
            "distance_mode": "Astrological house counting (same house = 1)",
            "raw_gap_mode": "Circular gap (same house = 0)",
        },
        "current_dasha": active_dasha,
        "rows": role_rows,
        "trail": {
            "birth_moon": {
                "house": imp_house,
                "sign": ((moon.get("sign") or {}).get("name", "—")) if isinstance(moon.get("sign"), dict) else moon.get("sign", "—"),
                "degree": moon.get("degree", 0),
                "minutes": moon.get("minutes", 0),
            },
            "imp_rashi_resolution": {
                "house_number_used": imp_house,
                "house_sign_found": imp_rashi or "—",
            },
            "current_planetary_timestamp": (current_positions or {}).get("as_of_local", "—"),
            "row_count": len(role_rows),
            "rows": role_rows,
        }
    }


async def fetch_current_planetary_positions(lat: float, lng: float) -> dict:
    token = await get_token()
    tz_name = get_timezone_name(lat, lng)
    tz = pytz.timezone(tz_name)
    current_local = datetime.now(tz)
    dt_iso = current_local.isoformat(timespec="seconds")
    coords = f"{lat},{lng}"

    print(f"\n[TRANSIT] /planet-position datetime={dt_iso} coords={coords}")

    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(
            "https://api.prokerala.com/v2/astrology/planet-position",
            headers={"Authorization": f"Bearer {token}"},
            params={
                "ayanamsa": 1,
                "coordinates": coords,
                "datetime": dt_iso,
                "la": "en",
            }
        )

    if r.status_code != 200:
        raise Exception(f"current planet-position API error {r.status_code}: {r.text}")

    snapshot = build_planet_position_snapshot(r.json().get("data", {}) or {})
    return {
        "as_of_local": current_local.isoformat(),
        "timezone": tz_name,
        "ascendant": snapshot.get("ascendant", {}),
        "planets": snapshot.get("planets", []),
    }


async def fetch_chart(lat: float, lng: float, dob: str, birth_time: str) -> dict:
    """
    Calls the Prokerala /kundli endpoint.
    Returns: { ascendant, planets, houses, svg_url }
    """
    token     = await get_token()
    tz_offset = get_timezone_offset(lat, lng)
    dt_iso    = f"{dob}T{birth_time}:00{tz_offset}"
    coords    = f"{lat},{lng}"

    print(f"\n[CHART] /kundli  datetime={dt_iso}  coords={coords}")

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Call 1: Get planetary data
        r = await client.get(
            "https://api.prokerala.com/v2/astrology/planet-position",
            headers={"Authorization": f"Bearer {token}"},
            params={
                "ayanamsa":    1,
                "coordinates": coords,
                "datetime":    dt_iso,
                "la":          "en"
            }
        )

        # Call 2: Get SVG Chart Image
        r_svg = await client.get(
            "https://api.prokerala.com/v2/astrology/chart",
            headers={"Authorization": f"Bearer {token}"},
            params={
                "ayanamsa":    1,
                "coordinates": coords,
                "datetime":    dt_iso,
                "chart_type":  "rasi",
                "chart_style": "south-indian",
                "la":          "en"
            }
        )

        # Call 3: Get birth details (nakshatra etc.)
        r_details = await client.get(
            "https://api.prokerala.com/v2/astrology/birth-details",
            headers={"Authorization": f"Bearer {token}"},
            params={
                "ayanamsa":    1,
                "coordinates": coords,
                "datetime":    dt_iso,
                "la":          "en"
            }
        )

        # Call 4: Get dasha periods
        r_dasha = await client.get(
            "https://api.prokerala.com/v2/astrology/dasha-periods",
            headers={"Authorization": f"Bearer {token}"},
            params={
                "ayanamsa":    1,
                "coordinates": coords,
                "datetime":    dt_iso,
                "la":          "en"
            }
        )

    print(f"   Data Status:    {r.status_code}")
    print(f"   SVG Status:     {r_svg.status_code}")
    print(f"   Details Status: {r_details.status_code}")
    print(f"   Dasha Status:   {r_dasha.status_code}")

    dasha_raw = {}
    if r_dasha.status_code == 200:
        dasha_raw = r_dasha.json().get("data",{})
        print(f"   Dasha keys: {list(dasha_raw.keys())}")
    else:
        print(f"   Dasha failed: {r_dasha.text[:200]}")

    if r.status_code != 200:
        print(f"   Error body: {r.text}")
        raise Exception(f"kundli API error {r.status_code}: {r.text}")

    data = r.json().get("data", {})

    # ── Nakshatra map ─────────────────────────────────────────────────────
    NAKSHATRAS = [
        "Ashwini","Bharani","Krithika","Rohini",
        "Mrigashira","Aridra","Punarvasu","Pushya",
        "Ashlesha","Magha","Purvaphalguni",
        "Uttara Phalguni","Hasta","Chitha","Swathi",
        "Vishaka","Anuradha","Jyesta","Moola",
        "Poorvashada","Uttaraashada","Shravana",
        "Dhanishta","Shathabhisha","Poorvabhadra",
        "Uttara Bhadrapada","Revathi"
    ]

    ZODIAC_IDX = {
        "Mesha": 0, "Vrishabha": 1, "Mithuna": 2, "Karka": 3,
        "Simha": 4, "Kanya": 5, "Tula": 6, "Vrischika": 7,
        "Dhanu": 8, "Makara": 9, "Kumbha": 10, "Meena": 11
    }

    def calc_nakshatra(sign_name, deg, mins):
        sign_idx = ZODIAC_IDX.get(sign_name, 0)
        full_lon = sign_idx * 30 + deg + mins / 60.0
        nk_idx  = int(full_lon / 13.3333) % 27
        pada    = int((full_lon % 13.3333) / 3.3333) + 1
        return {"name": NAKSHATRAS[nk_idx], "pada": min(pada, 4)}

    # birth-details only returns the Lagna nakshatra, NOT per-planet nakshatra.
    # So we always calculate nakshatra from planet longitude for all planets.
    print("   Calculating nakshatra from planet longitudes")
    nakshatra_map = {}
    for p in data.get("planet_position", []):
        pname     = p.get("name", "")
        sign_name = p.get("rasi", {}).get("name", "Mesha")
        deg_raw   = p.get("degree", 0)
        deg       = int(deg_raw)
        mins      = int((deg_raw % 1) * 60)
        nakshatra_map[pname] = calc_nakshatra(sign_name, deg, mins)
    print(f"   Nakshatras calculated for: {list(nakshatra_map.keys())}")

    # ── Planets and Ascendant ──────────────────────────────────────────────────
    planets = []
    ascendant = {}
    
    # First pass: Identify Ascendant
    for p in data.get("planet_position", []):
        if p.get("name") == "Ascendant":
            asc_id = p.get("rasi", {}).get("id", 0)
            nk_data = nakshatra_map.get("Ascendant", {"name": "—", "pada": ""})
            ascendant = {
                "name": p.get("rasi", {}).get("name", "—"),
                "id": asc_id,
                "house": 1,
                "nakshatra": nk_data,
                "nakshatra_pada": nk_data.get("pada", 1)
            }
            break

    asc_position = ascendant["id"] + 1 if "id" in ascendant else 1

    # Second pass: Process all planets
    for p in data.get("planet_position", []):
        pname = p.get("name", "")
        if pname == "Ascendant":
            planets.append({
                "name":         "Ascendant",
                "house":        1,
                "sign":         {"name": p.get("rasi", {}).get("name", "—")},
                "degree":       int(p.get("degree", 0)),
                "minutes":      int((p.get("degree", 0) % 1) * 60),
                "nakshatra":    nakshatra_map.get("Ascendant", {"name": "—", "pada": ""}),
                "isRetrograde": False,
            })
            continue

        planet_position = p.get("position", 1)
        house_number = ((planet_position - asc_position) % 12) + 1

        planets.append({
            "name":         pname,
            "house":        house_number,
            "sign":         {"name": p.get("rasi", {}).get("name", "—")},
            "degree":       int(p.get("degree", 0)),
            "minutes":      int((p.get("degree", 0) % 1) * 60),
            "nakshatra":    nakshatra_map.get(pname, {"name": "—", "pada": ""}),
            "isRetrograde": p.get("is_retrograde", False),
        })

    # ── Houses (calculated from Ascendant) ───────────────────────────────────
    ZODIAC = ["", "Mesha", "Vrishabha", "Mithuna",
              "Karka", "Simha", "Kanya", "Tula",
              "Vrischika", "Dhanu", "Makara",
              "Kumbha", "Meena"]

    houses = []
    if "id" in ascendant:
        for i in range(12):
            sign_pos = ((asc_position - 1 + i) % 12) + 1
            houses.append({
                "house": i + 1,
                "sign":  {"name": ZODIAC[sign_pos]}
            })

    # ── Chart SVG image from second API call ──────────────────────────────────
    svg_raw = ""
    if r_svg.status_code == 200:
        svg_raw = r_svg.text

    print(f"[OK] Chart ready — {len(planets)} planets | {len(houses)} houses | asc={ascendant.get('name','?')} | svg={'yes' if svg_raw else 'no'}")

    return {
        "planets":   planets,
        "houses":    houses,
        "ascendant": ascendant,
        "svg_raw":   svg_raw,
        "dasha_raw": dasha_raw
    }



# ══════════════════════════════════════════════════════════════
# SERVE FRONTEND ROUTES
# ══════════════════════════════════════════════════════════════
@app.route("/")
def index():
    return send_from_directory(
        ".", "astrohealth-landing.html")

@app.route("/results")
def results_page():
    return send_from_directory(
        ".", "results.html")

@app.route("/results.html")
def results_html():
    return send_from_directory(
        ".", "results.html")

@app.route("/print_report.js")
def print_report_js():
    return send_from_directory(
        ".", "print_report.js")

@app.route("/print-report")
@app.route("/print_report.html")
def print_report_html():
    return send_from_directory(
        ".", "print_report.html")

@app.route("/priority6")
def priority6_page():
    return send_from_directory(
        ".", "priority6.html")

@app.route("/favicon.ico")
def favicon():
    return "", 204


def _read_json_if_exists(path: str):
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        return _json.load(f)


def _resolve_patient_gender(chart_data=None, diagnosis=None, payload=None, processed=None, raw_chart=None):
    for source in (chart_data, diagnosis, payload, processed, raw_chart):
        if not isinstance(source, dict):
            continue
        gender = source.get("gender")
        if normalize_gender(gender):
            return gender
    return ""


def _build_latest_patient_payload(patient_id: str) -> dict:
    folder = os.path.join("patients", str(patient_id))
    chart_data = _read_json_if_exists(os.path.join(folder, "chart_data.json"))
    processed = _read_json_if_exists(os.path.join(folder, "processed_logic.json"))
    diagnosis = _read_json_if_exists(os.path.join(folder, "diagnosis.json"))
    raw_dasha = _read_json_if_exists(os.path.join(folder, "raw_dasha.json"))
    raw_chart = _read_json_if_exists(os.path.join(folder, "raw_chart.json"))

    payload = {}
    if raw_chart:
        payload.update({
            "name": raw_chart.get("name", ""),
            "dob": raw_chart.get("dob", ""),
            "birth_time": raw_chart.get("birth_time", ""),
            "birth_place": raw_chart.get("birth_place", raw_chart.get("place", "")),
        })

    if processed:
        payload.update({
            "ascendant": processed.get("ascendant", {}),
            "planets": processed.get("planets", []),
            "houses": processed.get("houses", []),
            "rule1": processed.get("rule1", {}),
            "dasha": processed.get("dasha", {}),
            "gender": processed.get("gender", ""),
            "complete_analysis": processed.get("complete_analysis", {}),
            "hitlist": processed.get("hitlist", {}),
            "most_probable": processed.get("most_probable", []),
            "top_diseases": processed.get("complete_analysis", {}).get("top_diseases", []),
            "rashi_correlation": processed.get("rashi_correlation", {}),
            "organ_truth_correlation": processed.get("organ_truth_correlation", {}),
            "common_findings": processed.get("common_findings", {}),
            "related_house_severity": processed.get("related_house_severity", {}),
            "dasha_chat_priority": processed.get("dasha_chat_priority", {}),
            "health_forecast": processed.get("health_forecast", []),
        })

    if chart_data:
        payload.update({
            "gender": chart_data.get("gender", payload.get("gender", "")),
            "disease_filter": chart_data.get("disease_filter", payload.get("disease_filter", {})),
            "rashi_correlation": chart_data.get("rashi_correlation", payload.get("rashi_correlation", {})),
            "current_planetary_positions": chart_data.get("current_planetary_positions", {}),
            "second_ascendant": chart_data.get("second_ascendant", {}),
            "imp_rashi_distance": chart_data.get("imp_rashi_distance", {}),
            "birth_current_distance": chart_data.get("birth_current_distance", {}),
        })

        if not payload.get("zone_analysis") and chart_data.get("second_ascendant"):
            try:
                payload["zone_analysis"] = run_zone_analysis(chart_data, chart_data.get("second_ascendant"))
            except Exception:
                payload["zone_analysis"] = {}

    current_dasha = payload.get("dasha") or {}
    if payload.get("rule1") and raw_dasha and not current_dasha.get("antardasha_groups"):
        try:
            dasha_raw_data = raw_dasha.get("dasha_data", {}).get("data", {})
            enriched_dasha = analyse_dasha(dasha_raw_data, payload.get("rule1", {}))
            current_dasha.update({
                "mahadasha_periods": enriched_dasha.get("mahadasha_periods", []),
                "antardasha_groups": enriched_dasha.get("antardasha_groups", []),
            })
            payload["dasha"] = current_dasha
        except Exception:
            pass

    df = payload.get("disease_filter") or {}
    eq = (df.get("relation_equation") or {}) if isinstance(df, dict) else {}
    if payload.get("rule1") and payload.get("dasha") and not eq:
        try:
            from rules import apply_disease_filter
            gender_value = _resolve_patient_gender(chart_data, diagnosis, payload, processed, raw_chart)
            payload["disease_filter"] = apply_disease_filter(payload.get("rule1", {}), payload.get("dasha", {}), gender=gender_value)
        except Exception:
            pass

    if diagnosis:
        payload["diagnosis"] = diagnosis

    if not payload.get("common_findings") and (payload.get("hitlist") or payload.get("rashi_correlation")):
        try:
            from common_findings_engine import build_common_findings
            payload["common_findings"] = build_common_findings(
                payload.get("hitlist", {}),
                payload.get("rashi_correlation", {}),
            )
        except Exception:
            payload["common_findings"] = {}

    if not payload.get("related_house_severity") and payload.get("rule1") and payload.get("dasha"):
        try:
            from related_house_severity_engine import build_related_house_severity
            payload["related_house_severity"] = build_related_house_severity(
                payload.get("rule1", {}),
                payload.get("dasha", {}),
                payload.get("planets", []),
            )
        except Exception:
            payload["related_house_severity"] = {}

    if payload.get("planets") and payload.get("rule1"):
        try:
            from organ_truth_correlation_engine import run_organ_truth_correlation_analysis
            gender_value = _resolve_patient_gender(chart_data, diagnosis, payload, processed, raw_chart)
            gender_code = normalize_gender(gender_value)
            live_chart = {
                "planets": payload.get("planets", []),
                "ascendant": payload.get("ascendant", {}),
                "houses": payload.get("houses", []),
            }
            payload["organ_truth_correlation"] = run_organ_truth_correlation_analysis(
                live_chart,
                payload.get("rule1", {}),
                gender=gender_code,
            )
        except Exception:
            pass
        try:
            from disease_first_logic import run_disease_first_logic, build_current_dasha_priority_sources
            gender_value = _resolve_patient_gender(chart_data, diagnosis, payload, processed, raw_chart)
            gender_code = normalize_gender(gender_value)
            live_chart = {
                "planets": payload.get("planets", []),
                "ascendant": payload.get("ascendant", {}),
                "houses": payload.get("houses", []),
            }
            payload["disease_first_logic"] = run_disease_first_logic(
                live_chart,
                payload.get("rule1", {}),
                gender=gender_code,
            )
            payload["current_dasha_priority_sources"] = build_current_dasha_priority_sources(
                live_chart,
                payload.get("rule1", {}),
                payload.get("dasha", {}),
                gender=gender_code,
            )
        except Exception:
            pass
        try:
            from disease_compare_logic import run_disease_compare_logic
            gender_value = _resolve_patient_gender(chart_data, diagnosis, payload, processed, raw_chart)
            gender_code = normalize_gender(gender_value)
            live_chart = {
                "planets": payload.get("planets", []),
                "ascendant": payload.get("ascendant", {}),
                "houses": payload.get("houses", []),
            }
            payload["disease_compare_logic"] = run_disease_compare_logic(
                live_chart,
                payload.get("rule1", {}),
                gender=gender_code,
            )
        except Exception:
            pass

    gender_value = _resolve_patient_gender(chart_data, diagnosis, payload, processed, raw_chart)
    payload["gender"] = gender_value or payload.get("gender", "")
    payload["kb_planet_diseases"] = filter_planet_diseases_by_gender(PLANET_DISEASES, gender_value)
    payload["kb_nakshatra_diseases"] = filter_nakshatra_diseases_by_gender(NAKSHATRA_DISEASES, gender_value)
    payload["kb_rashi_organs"] = filter_rashi_organs_by_gender(RASHI_ORGANS, gender_value)
    payload["kb_nakshatra_lords"] = dict(NAKSHATRA_LORDS)

    try:
        def _nk_name(obj):
            nk = (obj or {}).get("nakshatra", {})
            if isinstance(nk, dict):
                return nk.get("name", "")
            return nk or ""

        def _nk_lord(name):
            return NAKSHATRA_LORDS.get(name, "—")

        planets = payload.get("planets", []) or []
        planets_by_name = {p.get("name"): p for p in planets if p.get("name")}
        rule1 = payload.get("rule1", {}) or {}

        sixth_occupants = []
        for occ in rule1.get("rogkaraka_1", []) or []:
            planet = planets_by_name.get(occ.get("name", ""))
            nk_name = _nk_name(planet)
            sixth_occupants.append({
                "planet": occ.get("name", "—"),
                "nakshatra": nk_name or "—",
                "lord": _nk_lord(nk_name) if nk_name else "—",
            })

        eleventh_occupants = []
        for planet in planets:
            if int(planet.get("house", 0) or 0) != 11:
                continue
            nk_name = _nk_name(planet)
            eleventh_occupants.append({
                "planet": planet.get("name", "—"),
                "nakshatra": nk_name or "—",
                "lord": _nk_lord(nk_name) if nk_name else "—",
            })

        sixth_lord_planet = planets_by_name.get(rule1.get("sixth_house_lord", ""))
        sixth_lord_nk = _nk_name(sixth_lord_planet)
        dispositor_planet = planets_by_name.get((rule1.get("rogkaraka_3") or {}).get("name", ""))
        dispositor_nk = _nk_name(dispositor_planet)
        asc_lord_planet = planets_by_name.get(rule1.get("ascendant_lord", ""))
        asc_lord_nk = _nk_name(asc_lord_planet)

        eleventh_lord_name = ""
        houses = payload.get("houses", []) or []
        eleventh_house = next((h for h in houses if int(h.get("house", 0) or 0) == 11), {}) or {}
        eleventh_sign = ((eleventh_house.get("sign") or {}).get("name", ""))
        sign_lords = {
            "Aries": "Mars", "Mesha": "Mars",
            "Taurus": "Venus", "Vrishabha": "Venus", "Rishabha": "Venus",
            "Gemini": "Mercury", "Mithuna": "Mercury", "Mithun": "Mercury",
            "Cancer": "Moon", "Karka": "Moon", "Kataka": "Moon",
            "Leo": "Sun", "Simha": "Sun",
            "Virgo": "Mercury", "Kanya": "Mercury",
            "Libra": "Venus", "Tula": "Venus",
            "Scorpio": "Mars", "Vrischika": "Mars", "Vrishchika": "Mars",
            "Sagittarius": "Jupiter", "Dhanu": "Jupiter", "Dhanur": "Jupiter",
            "Capricorn": "Saturn", "Makara": "Saturn",
            "Aquarius": "Saturn", "Kumbha": "Saturn",
            "Pisces": "Jupiter", "Meena": "Jupiter",
        }
        eleventh_lord_name = sign_lords.get(eleventh_sign, "")
        eleventh_lord_planet = planets_by_name.get(eleventh_lord_name, {})
        eleventh_lord_nk = _nk_name(eleventh_lord_planet)

        payload["nakshatra_lord_reference"] = {
            "sixth_occupants": sixth_occupants,
            "sixth_lord": {
                "planet": rule1.get("sixth_house_lord", "—"),
                "nakshatra": sixth_lord_nk or "—",
                "lord": _nk_lord(sixth_lord_nk) if sixth_lord_nk else "—",
            },
            "dispositor": {
                "planet": (rule1.get("rogkaraka_3") or {}).get("name", "—"),
                "nakshatra": dispositor_nk or "—",
                "lord": _nk_lord(dispositor_nk) if dispositor_nk else "—",
            },
            "ascendant_lord": {
                "planet": rule1.get("ascendant_lord", "—"),
                "nakshatra": asc_lord_nk or "—",
                "lord": _nk_lord(asc_lord_nk) if asc_lord_nk else "—",
            },
            "eleventh_occupants": eleventh_occupants,
            "eleventh_lord": {
                "planet": eleventh_lord_name or "—",
                "nakshatra": eleventh_lord_nk or "—",
                "lord": _nk_lord(eleventh_lord_nk) if eleventh_lord_nk else "—",
            },
        }
    except Exception:
        payload["nakshatra_lord_reference"] = {}

    apply_bhadravathi_overrides(payload, raw_chart or payload)
    apply_person2_overrides(payload, raw_chart or payload)
    return payload


# ══════════════════════════════════════════════════════════════
# POST /generate-chart
# ══════════════════════════════════════════════════════════════
@app.route("/generate-chart", methods=["POST"])
@require_auth(rate_limit="chart")
def generate_chart():
    try:
        body = request.get_json(force=True)
        chart_input = parse_chart_input(body)
        name = chart_input["name"]
        dob = chart_input["dob"]
        birth_time = chart_input["birth_time"]
        lat = chart_input["lat"]
        lng = chart_input["lng"]
        birth_place = chart_input["birth_place"]
        father_name = chart_input["father_name"]
        mother_name = chart_input["mother_name"]
        gender = chart_input["gender"]

        log.info(
            "chart_requested",
            extra={"request_id": getattr(g, "request_id", ""), "internal_user_id": g.user["internal_user_id"], "operation": "generate_chart"},
        )

        # Step 1: Fetch and save raw data
        fetch_result = asyncio.run(fetch_and_save(
            name       = name,
            dob        = dob,
            birth_time = birth_time,
            lat        = lat,
            lng        = lng,
            place      = birth_place,
            gender     = gender,
            father_name = father_name,
            mother_name = mother_name,
            owner_id   = g.user["internal_user_id"],
        ))

        patient_id = fetch_result["patient_id"]
        source     = fetch_result.get("source", "Unknown")
        print(f"Data Source: {source}")
        print(f"Patient ID: {patient_id}")

        # Step 2: Run logic processing
        processed = run_logic(patient_id)

        # Step 3: Run disease diagnosis
        diagnosis = run_diagnose(patient_id)

        current_planetary_positions = asyncio.run(fetch_current_planetary_positions(lat, lng))
        second_ascendant = calculate_second_ascendant(
            dob=dob,
            birth_time=birth_time,
            lat=lat,
            lng=lng,
            planets=fetch_result["planets"],
            houses=fetch_result["houses"],
        )
        # Step 4: Run zone analysis
        zone_analysis = run_zone_analysis(fetch_result, second_ascendant)
        imp_rashi_distance = build_imp_rashi_distance_analysis(
            fetch_result,
            processed["rule1"],
            current_planetary_positions,
            processed["dasha"],
        )
        birth_current_distance = build_birth_current_distance_analysis(
            fetch_result,
            processed["rule1"],
            current_planetary_positions,
            processed["dasha"],
        )

        from rules import apply_disease_filter
        disease_filter = apply_disease_filter(processed["rule1"], processed["dasha"], gender=gender)

        chart_data_path = f"patients/{patient_id}/chart_data.json"
        with open(chart_data_path, "w") as f:
            _json.dump({
                **fetch_result,
                "rule1":           processed["rule1"],
                "dasha":           processed["dasha"],
                "complete":        processed["complete_analysis"],
                "disease_filter":  disease_filter,
                "rashi_correlation": processed.get("rashi_correlation", {}),
                "organ_truth_correlation": processed.get("organ_truth_correlation", {}),
                "dasha_chat_priority": processed.get("dasha_chat_priority", {}),
                "zone_analysis":   zone_analysis,
                "current_planetary_positions": current_planetary_positions,
                "second_ascendant": second_ascendant,
                "imp_rashi_distance": imp_rashi_distance,
                "birth_current_distance": birth_current_distance,
            }, f, indent=2)

        processed_file = f"patients/{patient_id}/processed_logic.json"
        with open(processed_file, "r") as f:
            proc_dict = _json.load(f)

        # --- Diagnostic Logic moved to rules.py ---
        most_probable = processed["complete_analysis"].get("most_probable", [])
        
        proc_dict["disease_filter"] = disease_filter
        proc_dict["most_probable"] = most_probable
        proc_dict["gender"] = gender
        proc_dict["second_ascendant"] = second_ascendant
        proc_dict["zone_analysis"] = zone_analysis
        proc_dict["imp_rashi_distance"] = imp_rashi_distance
        proc_dict["birth_current_distance"] = birth_current_distance

        with open(processed_file, "w") as f:
            _json.dump(proc_dict, f, indent=2)

        # Build mappings for legacy UI components if needed
        rule1_result = processed["rule1"]
        nakshatra_diseases = {}
        planet_diseases = {}
        rk_planets = (
            rule1_result.get("rogkaraka_1", []) +
            ([rule1_result["rogkaraka_2"]] if rule1_result.get("rogkaraka_2") else []) +
            ([rule1_result["rogkaraka_3"]] if rule1_result.get("rogkaraka_3") else [])
        )
        conditional_moon = rule1_result.get("conditional_moon") or {}
        if conditional_moon.get("include") and (conditional_moon.get("planet") or {}).get("name") == "Moon":
            rk_planets.append(conditional_moon["planet"])
        for p in rk_planets:
            if p.get("name"):
                nakshatra_diseases[p["name"]] = filter_terms_by_gender(
                    get_nakshatra_diseases(p.get("nakshatra"), p.get("nakshatra_pada")),
                    gender,
                )
                diseases = PLANET_DISEASES.get(p["name"], [])
                planet_diseases[p["name"]] = filter_terms_by_gender(diseases, gender)

        # Step 4: Build response exactly as before
        payload = {
            "success":           True,
            "name":              name,
            "dob":               dob,
            "birth_time":        birth_time,
            "birth_place":       birth_place,
            "father_name":       father_name,
            "mother_name":       mother_name,
            "gender":            gender,
            "lat":               lat,
            "lng":               lng,
            "patient_id":        patient_id,
            "ascendant":         fetch_result["ascendant"],
            "planets":           fetch_result["planets"],
            "houses":            fetch_result["houses"],
            "svg_raw":           fetch_result["svg_raw"],
            "rule1":             processed["rule1"],
            "dasha":             processed["dasha"],
            "complete_analysis": processed["complete_analysis"],
            "disease_filter":    disease_filter,
            "hitlist":           processed.get("hitlist", {}),
            "rashi_correlation": processed.get("rashi_correlation", {}),
            "organ_truth_correlation": processed.get("organ_truth_correlation", {}),
            "dasha_chat_priority": processed.get("dasha_chat_priority", {}),
            "nakshatra_diseases": nakshatra_diseases,
            "planet_diseases":   planet_diseases,
            "kb_planet_diseases": filter_planet_diseases_by_gender(PLANET_DISEASES, gender),
            "kb_nakshatra_diseases": filter_nakshatra_diseases_by_gender(NAKSHATRA_DISEASES, gender),
            "kb_rashi_organs": filter_rashi_organs_by_gender(RASHI_ORGANS, gender),
            "most_probable":     most_probable,
            "top_diseases":      processed["complete_analysis"].get("top_diseases", []),
            "diagnosis":         diagnosis,
            "zone_analysis":     zone_analysis,
            "current_planetary_positions": current_planetary_positions,
            "second_ascendant":  second_ascendant,
            "imp_rashi_distance": imp_rashi_distance,
            "birth_current_distance": birth_current_distance,
            "health_forecast":   processed.get("health_forecast", []),
            "data_source":       source,
        }
        lineage = get_services().persistence.save_generation(
            g.user["internal_user_id"],
            chart_input,
            patient_id,
            source,
            payload,
        )
        payload["input_id"] = lineage["input_id"]
        return jsonify(payload)

    except (RequestValidationError, UpstreamError, AuthorizationError, HTTPException):
        raise
    except Exception:
        log.error("chart_failed", extra={"request_id": getattr(g, "request_id", ""), "operation": "generate_chart"})
        return safe_failure()



# GET /health
@app.get("/health")
# @basic_auth.exempt
def health():
    return jsonify({
        "status": "ok",
        "server": "AstroMedica"
    })



@app.get("/ready")
def ready():
    ok, checks = get_services().ready()
    return jsonify({"status": "ready" if ok else "not_ready", "checks": checks}), (200 if ok else 503)


@app.get("/public-config")
def public_config():
    settings = get_services().settings
    return jsonify({
        "clerkPublishableKey": settings.clerk_publishable_key,
        "frontendUrl": settings.frontend_url,
    })


@app.get("/me/records")
@require_auth(rate_limit="read")
def my_records():
    records = get_services().repository.list_records(g.user["internal_user_id"])
    return jsonify({"success": True, "records": records})


@app.get("/patient-data/<patient_id>")
@require_auth(rate_limit="read")
def patient_data(patient_id):
    try:
        enforce_patient_access(patient_id)
        payload = _build_latest_patient_payload(patient_id)
        if not payload:
            return jsonify({"success": False, "error": "Not found."}), 404
        return jsonify({"success": True, "patient_id": patient_id, "data": payload})
    except Exception:
        raise


@app.get("/priority6-data/<patient_id>")
@require_auth(rate_limit="read")
def priority6_data(patient_id):
    """
    New priority-cascade page. Pulls ONLY the cached patient/chart facts
    (ascendant, planets, houses, rule1, dasha, gender, name/dob/birth_time/
    birth_place) from the existing cache -- never the old disease/organ
    logic outputs. The 5 new v2 algorithms + v2 combined summary are always
    computed fresh, with no chart-specific overrides applied.
    """
    try:
        enforce_patient_access(patient_id)
        payload = _build_latest_patient_payload(patient_id)
        if not payload:
            return jsonify({"success": False, "error": "Not found."}), 404

        folder = os.path.join("patients", str(patient_id))
        cached_chart_data = _read_json_if_exists(os.path.join(folder, "chart_data.json")) or {}
        shadbala = _read_json_if_exists(os.path.join(folder, "shadbala.json")) or {}

        chart_facts = {
            "name": payload.get("name", ""),
            "dob": payload.get("dob", ""),
            "birth_time": payload.get("birth_time", ""),
            "birth_place": payload.get("birth_place", ""),
            "ascendant": payload.get("ascendant", {}),
            "planets": payload.get("planets", []),
            "houses": payload.get("houses", []),
            "dasha": payload.get("dasha", {}),
            "gender": payload.get("gender", ""),
            "svg_raw": cached_chart_data.get("svg_raw", ""),
        }
        rule1_result = payload.get("rule1", {}) or {}
        gender = payload.get("gender", "")

        combined_v2 = build_combined_algo_summary_v2(chart_facts, rule1_result, gender)
        cascade_view = build_full_cascade_view(rule1_result)
        cascade_detail = build_cascade_tiers(chart_facts, rule1_result, gender)
        drishti_detail = build_drishti_catalysts(chart_facts, rule1_result, gender)
        ascendant_reference = build_ascendant_reference(chart_facts, rule1_result, gender)
        second_house_reference = build_house_occupant_reference(chart_facts, rule1_result, 2, gender)
        disease_priority_cascade = run_disease_priority_cascade_logic(chart_facts, rule1_result, gender)
        disease_priority_cascade_v2 = run_disease_priority_cascade_logic_v2(chart_facts, rule1_result, gender)
        organ_priority_v2 = build_organ_priority_view(disease_priority_cascade_v2)
        shadbala_weighted_priority = run_shadbala_weighted_disease_priority(chart_facts, rule1_result, shadbala, gender)
        dasha_weighted_priority = run_dasha_weighted_disease_priority(chart_facts, rule1_result, chart_facts.get("dasha", {}), gender)

        return jsonify({
            "success": True,
            "patient_id": patient_id,
            "cascade_view": cascade_view,
            "cascade_detail": cascade_detail,
            "drishti_detail": drishti_detail,
            "ascendant_reference": ascendant_reference,
            "second_house_reference": second_house_reference,
            "chart": chart_facts,
            "rule1": rule1_result,
            "combined_algo_summary_v2": combined_v2,
            "shadbala": shadbala,
            "disease_priority_cascade": disease_priority_cascade,
            "disease_priority_cascade_v2": disease_priority_cascade_v2,
            "organ_priority_v2": organ_priority_v2,
            "shadbala_weighted_priority": shadbala_weighted_priority,
            "dasha_weighted_priority": dasha_weighted_priority,
        })
    except (RequestValidationError, AuthorizationError, HTTPException):
        raise
    except Exception:
        log.error("priority6_failed", extra={"request_id": getattr(g, "request_id", ""), "operation": "priority6"})
        return safe_failure()


async def call_gemini(
    system_prompt: str,
    conversation:  list
) -> str:
    """
    Calls Gemini APIs with full
    conversation history.
    Returns AI response text.
    """
    url = (
        f"https://generativelanguage.googleapis"
        f".com/v1beta/models/{GEMINI_MODEL}"
        f":generateContent"
        f"?key={GEMINI_API_KEY}"
    )

    # Build contents from conversation history
    contents = []

    for msg in conversation:
        role = msg["role"]
        text = msg["content"]

        # Gemini uses "user" and "model" roles
        gemini_role = (
            "model" if role == "assistant"
            else "user"
        )

        contents.append({
            "role":  gemini_role,
            "parts": [{"text": text}]
        })

    if "gemma" in GEMINI_MODEL.lower():
        if contents and contents[0]["role"] == "user":
            orig = contents[0]["parts"][0]["text"]
            contents[0]["parts"][0]["text"] = f"{system_prompt}\n\n[USER]: {orig}"
        else:
            contents.insert(0, {
                "role": "user",
                "parts": [{"text": f"{system_prompt}\n\n[USER]: Hello. Please begin."}]
            })
            
        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature":     0.7,
                "maxOutputTokens": 1200,
                "topP":            0.95
            }
        }
    else:
        payload = {
            "system_instruction": {
                "parts": [{"text": system_prompt}]
            },
            "contents": contents,
            "generationConfig": {
                "temperature":     0.7,
                "maxOutputTokens": 1200,
                "topP":            0.95
            }
        }

    async with httpx.AsyncClient() as client:
        r = await client.post(
            url,
            json=payload,
            timeout=30.0
        )

    if r.status_code != 200:
        if r.status_code == 429:
            print("[Warning] Gemini Rate Limit Exceeded.")
            return _json_fallback_message(
                "I am experiencing high traffic right now and need to catch my breath. Please wait just a moment and try sending your message again."
            )
            
        if r.status_code in [401, 403]:
            log.error("gemini_auth_failed", extra={"operation": "gemini", "status": r.status_code})
            raise UpstreamError("gemini")

        log.error("gemini_failed", extra={"operation": "gemini", "status": r.status_code})
        raise UpstreamError("gemini")

    data = r.json()
    
    # Safely extract text, handling potential safety blocks
    try:
        candidate = data.get("candidates", [])[0]
        
        # Check if blocked by safety
        if candidate.get("finishReason") == "SAFETY":
            print("[Warning] Gemini blocked response due to SAFETY.")
            return _json_fallback_message(
                "I apologize, but I am unable to discuss this specific symptom further. Could we focus on your general wellness routine or daily habits instead?"
            )
            
        response = candidate["content"]["parts"][0]["text"]
    except (IndexError, KeyError) as e:
        print(f"Gemini API unexpected format: {data}")
        raise Exception(f"Failed to parse Gemini response: {str(e)}")
        
    print(f"[OK] Gemini response "
          f"({len(response)} chars)")

    # Safely strip markdown code blocks if the AI accidentally adds them
    if response.strip().startswith("```"):
        import re
        # This matches ```json {data} ``` or just ``` {data} ```
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response, re.DOTALL)
        if match:
            response = match.group(1)

    return response.strip()

@app.route("/start-consultation", methods=["POST"])
@require_auth(rate_limit="chat")
def start_consultation():
    """
    Starts a new AI health consultation.
    Reads patient data from files via chat_module.
    """
    try:
        body = request.get_json(force=True)

        session_id = require_session_id(body.get("session_id", ""))
        patient_id = body.get("patient_id", "")
        enforce_patient_access(patient_id)
        get_services().session_owners[session_id] = {
            "internal_user_id": g.user["internal_user_id"],
            "patient_id": patient_id,
        }

        log.info("consultation_started", extra={"request_id": getattr(g, "request_id", ""), "operation": "start_consultation"})

        opening_result = chat_start(
            session_id,
            patient_id,
            conversation_store,
            call_gemini
        )

        get_services().persistence.save_chat_turn(
            g.user["internal_user_id"], session_id, patient_id, "assistant", opening_result["response"], 1
        )
        return jsonify({
            "success":  True,
            "response": opening_result["response"],
            "turn":     1,
            "is_final": False,
            "chat_debug": opening_result.get("debug_context", {})
        })

    except (RequestValidationError, AuthorizationError, UpstreamError, HTTPException):
        raise
    except Exception:
        log.error("consultation_failed", extra={"request_id": getattr(g, "request_id", ""), "operation": "start_consultation"})
        return safe_failure()

@app.route("/send-message", methods=["POST"])
@require_auth(rate_limit="chat")
def send_message():
    """
    Handles each patient message via chat_module.
    """
    try:
        body = request.get_json(force=True)

        session_id = require_session_id(body.get("session_id", ""))
        user_message = parse_chat_message(body.get("message", ""))
        owner = get_services().session_owners.get(session_id)
        if not owner or owner["internal_user_id"] != g.user["internal_user_id"]:
            return jsonify({"success": False, "error": "Not found."}), 404
        enforce_patient_access(owner["patient_id"])

        if session_id not in conversation_store:
            return jsonify({"success": False, "error": "Session not found."}), 400

        result = chat_send_message(
            session_id,
            user_message,
            conversation_store,
            call_gemini
        )

        # Deferred cleanup after final
        if result["is_final"]:
            import threading
            def cleanup():
                import time
                time.sleep(120)
                if session_id in conversation_store:
                    del conversation_store[session_id]
            threading.Thread(target=cleanup, daemon=True).start()

        get_services().persistence.save_chat_turn(
            g.user["internal_user_id"],
            session_id,
            owner["patient_id"],
            "user",
            user_message,
            result["turn"],
        )
        return jsonify({
            "success":  True,
            "response": result["response"],
            "turn":     result["turn"],
            "is_final": result["is_final"],
            "chat_debug": result.get("debug_context", {})
        })

    except (RequestValidationError, AuthorizationError, UpstreamError, HTTPException):
        raise
    except Exception:
        log.error("message_failed", extra={"request_id": getattr(g, "request_id", ""), "operation": "send_message"})
        return safe_failure()



@app.route("/combine-output", methods=["POST"])
@require_auth(rate_limit="chart")
def combine_output():
    """
    Module C aggregation endpoint.
    Synthesizes diagnosis and chat history into final_output.json.
    """
    try:
        body = request.get_json(force=True)
        patient_id = body.get("patient_id")
        enforce_patient_access(patient_id)

        # Verify chat log exists
        log_file = f"patients/{patient_id}/chat_log.json"
        if not os.path.exists(log_file):
            return jsonify({
                "success": False, 
                "error": "Chat record not found for this patient."
            }), 400

        print(f"🔄 Aggregating data for patient {patient_id}...")
        result = run_combine(patient_id)

        if not result:
            return jsonify({
                "success": False, 
                "error": "Aggregation engine failed to produce output."
            }), 500

        get_services().persistence.save_combined_module(g.user["internal_user_id"], patient_id, result)
        return jsonify({
            "success": True,
            "final_output": result
        })

    except (RequestValidationError, AuthorizationError, HTTPException):
        raise
    except Exception:
        log.error("combine_failed", extra={"request_id": getattr(g, "request_id", ""), "operation": "combine_output"})
        return safe_failure()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))

    print(f"[START] Binding to 0.0.0.0:{port}")

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )

