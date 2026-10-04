#!/usr/bin/env python3
"""
Module C — Output Aggregation
Aggregates diagnosis.json, chat_log.json, and processed_logic.json
to produce a final actionable health report.
"""

import os
import json
from datetime import datetime, timedelta
from symptom_mapper import extract_cluster_terms

# ── Risk Grade Constants ───────────────────────────────────────
RISK_GRADES = {
    "VERY_HIGH": {
        "min_score":  15,
        "label":      "Very High Risk",
        "color":      "#DC2626",
        "action":     "Immediate medical attention strongly advised"
    },
    "HIGH": {
        "min_score":  8,
        "label":      "Serious Risk",
        "color":      "#EF4444",
        "action":     "Consult a doctor within 2-4 weeks"
    },
    "MODERATE": {
        "min_score":  6,
        "label":      "Moderate Risk",
        "color":      "#F59E0B",
        "action":     "Monitor closely, Ayurvedic care advised"
    },
    "LOW": {
        "min_score":  3,
        "label":      "Low Risk",
        "color":      "#22C55E",
        "action":     "Preventive care and lifestyle awareness"
    },
    "VERY_LOW": {
        "min_score":  0,
        "label":      "Very Low Risk",
        "color":      "#4ADE80",
        "action":     "General wellness maintenance"
    }
}

# ── Recommendation Tables ──────────────────────────────────────
FOOD_TABLE = {
    "Vatha": {
        "avoid": [
            "raw vegetables", "cold foods", "carbonated drinks", "beans",
            "dry snacks", "caffeine"
        ],
        "vegetarian": {
            "eat": [
                "warm cooked foods", "ghee and sesame oil",
                "sweet fruits like mango banana", "warm milk with turmeric",
                "rice and wheat", "root vegetables", "nuts and seeds"
            ]
        },
        "non_vegetarian": {
            "eat": [
                "chicken soup", "warm fish curry", "eggs", "bone broth"
            ]
        }
    },
    "Pittha": {
        "avoid": [
            "spicy food", "sour food", "fried food", "alcohol",
            "red meat", "excess salt", "fermented food"
        ],
        "vegetarian": {
            "eat": [
                "cooling foods like cucumber", "coconut water",
                "sweet fruits like melons", "leafy greens",
                "milk and butter", "basmati rice", "coriander and fennel"
            ]
        },
        "non_vegetarian": {
            "eat": [
                "white fish", "chicken (not spicy)", "egg whites"
            ]
        }
    },
    "Kapha": {
        "avoid": [
            "heavy oily foods", "dairy excess", "sweets", "cold drinks",
            "wheat excess", "fried foods", "red meat"
        ],
        "vegetarian": {
            "eat": [
                "light spicy warm foods", "honey", "ginger tea",
                "lentils and legumes", "leafy vegetables",
                "barley and millet", "bitter gourd"
            ]
        },
        "non_vegetarian": {
            "eat": [
                "lean chicken grilled", "fish (light preparation)", "eggs (boiled not fried)"
            ]
        }
    }
}

LIFESTYLE_TABLE = {
    "Vatha": [
        "Sleep before 10 PM, wake by 6 AM",
        "Warm oil massage (sesame) daily",
        "Avoid cold and windy environments",
        "Gentle yoga and walking — no intense exercise",
        "Meditation 10 minutes daily",
        "Keep warm — especially feet and lower back",
        "Eat at fixed times — no skipping meals"
    ],
    "Pittha": [
        "Avoid direct sun between 10 AM and 2 PM",
        "Cool water bath in morning",
        "Avoid anger and stressful situations",
        "Moderate exercise — swimming or walking",
        "Eat on time — never skip meals",
        "Coconut oil massage weekly",
        "Spend time in nature — near water"
    ],
    "Kapha": [
        "Wake before 6 AM — avoid oversleeping",
        "Vigorous exercise daily — running or cycling",
        "Dry massage (garshana) with silk gloves",
        "Avoid daytime sleeping",
        "Keep environment warm and dry",
        "Intermittent fasting beneficial",
        "Stay socially active — avoid isolation"
    ]
}

WELLNESS_TABLE = {
    "Vatha": [
        "Ashwagandha supplement daily",
        "Triphala at bedtime",
        "Warm ginger and honey tea morning",
        "Pranayama — Nadi Shodhana breathing"
    ],
    "Pittha": [
        "Shatavari supplement",
        "Amla juice daily",
        "Brahmi for mental cooling",
        "Chandra Namaskar (moon salutation)"
    ],
    "Kapha": [
        "Trikatu (ginger, pepper, pippali)",
        "Honey with warm water morning",
        "Surya Namaskar daily",
        "Dry ginger and turmeric milk"
    ]
}


# ── Internal Logic Functions ──────────────────────────────────

def get_risk_grade(score: float) -> dict:
    if score >= 15:
        return RISK_GRADES["VERY_HIGH"]
    elif score >= 10:
        return RISK_GRADES["HIGH"]
    elif score >= 6:
        return RISK_GRADES["MODERATE"]
    elif score >= 3:
        return RISK_GRADES["LOW"]
    else:
        return RISK_GRADES["VERY_LOW"]


def calculate_disease_probability(diagnosis: dict, chat_log: dict) -> list:
    from knowledge_base import PLANET_DISEASES

    # Weighted Base Score
    score_ctx = diagnosis.get("risk_score", {})
    wbs = (
        score_ctx.get("step_a", 0) * 0.4 +
        score_ctx.get("step_b", 0) * 0.3 +
        score_ctx.get("step_c", 0) * 0.3
    )

    # Keywords for Chat Score
    body_systems = [s.strip().lower() for s in diagnosis.get("body_systems", [])]
    dosha_symptoms_text = " ".join(diagnosis.get("dosha_symptoms", {}).values()).lower()
    
    keywords = []
    for s in body_systems:
        keywords += [k.strip() for k in s.split(",")]
    keywords += [k.strip() for k in dosha_symptoms_text.split(",")]
    keywords = list(set([k for k in keywords if k]))

    # Scan chat for matches
    chat_score_total = 0
    matched_keywords = []
    user_msgs = [t["message"].lower() for t in chat_log.get("turns", []) if t["role"] == "user"]
    
    for kw in keywords:
        for msg in user_msgs:
            if kw in msg:
                chat_score_total += 1
                matched_keywords.append(kw)
                break # count each keyword once

    chat_score_total = min(chat_score_total, 5)

    # Calculate for each condition in high_risk_conditions
    active_dasha_planets = [a["planet"] for a in diagnosis.get("active_dasha_alerts", [])]
    
    results = []
    for cond in diagnosis.get("high_risk_conditions", []):
        # Dasha Multiplier check
        multiplier = 1.0
        for planet in active_dasha_planets:
            planet_sys = PLANET_DISEASES.get(planet, "").lower()
            if cond.lower() in planet_sys:
                multiplier = 1.5
                break

        final_score = (wbs + chat_score_total) * multiplier
        grade_info = get_risk_grade(final_score)

        results.append({
            "condition":         cond,
            "base_score":        round(wbs, 1),
            "chat_score":        chat_score_total,
            "dasha_multiplier":  multiplier,
            "final_score":       round(final_score, 1),
            "grade":             [g for g in RISK_GRADES if RISK_GRADES[g]["label"] == grade_info["label"]][0],
            "grade_label":       grade_info["label"],
            "grade_color":       grade_info["color"],
            "action":            grade_info["action"],
            "matched_keywords":  list(set(matched_keywords))
        })

    return results


def calculate_care_period(diagnosis: dict, chat_log: dict, logic: dict) -> dict:
    # 1. Dasha End Dates
    alerts = diagnosis.get("active_dasha_alerts", [])
    end_dates = []
    for a in alerts:
        try:
            end_dates.append(datetime.strptime(a["end_date"], "%Y-%m-%d"))
        except: pass
    
    if not end_dates:
        primary_until = datetime.now() + timedelta(days=365)
    else:
        primary_until = max(end_dates)

    # 2. Chronic Indicators
    chronic_keywords = [
        "months", "years", "since", "long", "chronic", 
        "recurring", "always", "never goes away"
    ]
    is_chronic = False
    for t in chat_log.get("turns", []):
        if t["role"] == "user":
            msg = t["message"].lower()
            if any(kw in msg for kw in chronic_keywords):
                is_chronic = True
                primary_until += timedelta(days=180) # +6 months
                break

    # 3. Pratyantardasha (from logic)
    p_dasha = logic.get("dasha", {}).get("pratyantardasha", {})
    review_date_str = p_dasha.get("end_date", "")
    if review_date_str:
        review_date = datetime.strptime(review_date_str, "%Y-%m-%d")
    else:
        review_date = datetime.now() + timedelta(days=90)

    duration = (primary_until - datetime.now()).days // 30

    return {
        "primary_care_until":  primary_until.strftime("%Y-%m-%d"),
        "review_date":         review_date.strftime("%Y-%m-%d"),
        "duration_months":     max(duration, 0),
        "basis":               "Active Dasha and symptom persistence",
        "chronic_indicator":   is_chronic,
        "recommendation":      f"Monitor health closely until {primary_until.strftime('%b %Y')}. Professional review suggested by {review_date.strftime('%b %Y')}."
    }


def get_food_recommendations(diagnosis: dict) -> dict:
    doshas = diagnosis.get("dosha_imbalance", [])
    avoid = []
    veg_eat = []
    non_veg_eat = []

    for d in doshas:
        entry = FOOD_TABLE.get(d, {})
        if entry:
            avoid += entry.get("avoid", [])
            veg_eat += entry.get("vegetarian", {}).get("eat", [])
            non_veg_eat += entry.get("non_vegetarian", {}).get("eat", [])

    return {
        "doshas":  doshas,
        "avoid":   list(set(avoid)),
        "vegetarian": {"eat": list(set(veg_eat))},
        "non_vegetarian": {"eat": list(set(non_veg_eat))},
        "note": f"Personalized diet for {', '.join(doshas)} constitution."
    }


def get_doctor_recommendation(disease_prob: list, diagnosis: dict, chat_log: dict) -> dict:
    # Logic based on requirements
    top_grade = "VERY_LOW"
    grades_priority = ["VERY_LOW", "LOW", "MODERATE", "HIGH", "VERY_HIGH"]
    
    high_count = 0
    for d in disease_prob:
        grade = d["grade"]
        if grades_priority.index(grade) > grades_priority.index(top_grade):
            top_grade = grade
        if grades_priority.index(grade) >= grades_priority.index("HIGH"):
            high_count += 1

    has_active_dasha = len(diagnosis.get("active_dasha_alerts", [])) > 0
    
    chronic_keywords = ["years", "chronic", "always", "recurring", "never goes away"]
    is_chronic = False
    for t in chat_log.get("turns", []):
        if t["role"] == "user" and any(kw in t["message"].lower() for kw in chronic_keywords):
            is_chronic = True
            break

    # Decision logic
    see_doctor = False
    urgency = "Not immediate"
    reasoning = "General wellness guidelines are sufficient."
    
    priority_level = grades_priority.index(top_grade)
    if has_active_dasha: priority_level += 1
    if is_chronic: priority_level += 1
    if high_count >= 2: see_doctor = True

    if priority_level >= 4: # Equivalent to HIGH/VERY_HIGH
        see_doctor = True
        urgency = "Within 2 weeks"
        reasoning = "Presence of high-risk indicators combined with active dasha and/or chronic history."
    elif priority_level >= 3: # MODERATE
        see_doctor = True
        urgency = "Within 4 weeks"
        reasoning = "Moderate risk alignment detected. Proactive screening recommended."
    
    return {
        "see_doctor": see_doctor,
        "urgency":    urgency,
        "reasoning":  reasoning,
        "specialist": "General Physician and Ayurvedic Practitioner",
        "score_basis": {
            "risk_grade": top_grade,
            "dasha_active": has_active_dasha,
            "chronic_found": is_chronic,
            "high_conditions": high_count
        }
    }


def get_lifestyle_recommendations(diagnosis: dict) -> list:
    doshas = diagnosis.get("dosha_imbalance", [])
    recs = []
    for d in doshas:
        recs += LIFESTYLE_TABLE.get(d, [])
    return list(set(recs))


def get_wellness_suggestions(diagnosis: dict) -> list:
    doshas = diagnosis.get("dosha_imbalance", [])
    recs = []
    for d in doshas:
        recs += WELLNESS_TABLE.get(d, [])
    return list(set(recs))


def build_hitlist_confirmation_summary(logic: dict, chat_log: dict) -> list:
    scores = chat_log.get("hitlist_cluster_scores", {}) or {}
    top4 = logic.get("hitlist", {}).get("top4", [])
    summary = []

    for index, cluster in enumerate(top4[:4], start=1):
        score_data = scores.get(str(index), {})
        support_score = score_data.get("score", 0)
        yes_strong = score_data.get("yes_strong", 0)
        yes_but = score_data.get("yes_but", 0)
        no_but = score_data.get("no_but", 0)
        no_strong = score_data.get("no_strong", 0)
        gate_status = score_data.get("status", "")

        if gate_status == "confirmed" or yes_strong >= 3:
            status = "Confirmed"
            confidence = "High"
        elif gate_status in ["drilldown", "suspected"] or yes_strong >= 1 or yes_but >= 1:
            status = "Possible"
            confidence = "Medium"
        elif gate_status == "rejected" or no_strong >= 2:
            status = "Rejected"
            confidence = "Low"
        else:
            status = "Not strongly supported"
            confidence = "Low"

        terms = extract_cluster_terms(cluster)
        answers = score_data.get("answers", [])
        confirmed = [
            a.get("answer", "")
            for a in answers
            if a.get("result") in ["yes_strong", "yes_but"]
        ]

        summary.append({
            "rank": index,
            "original_rank": index,
            "system": cluster.get("label", f"Cluster {index}"),
            "hitlist_score": cluster.get("score", 0),
            "convergence": cluster.get("convergence", 0),
            "status": status,
            "confidence": confidence,
            "gate_status": gate_status,
            "support_score": support_score,
            "yes_strong": yes_strong,
            "yes_but": yes_but,
            "no_but": no_but,
            "no_strong": no_strong,
            "confirmed_patient_signals": confirmed[:4],
            "internal_organs": terms.get("organs", []),
            "internal_diseases": terms.get("diseases", []),
            "confirmed_organs": score_data.get("confirmed_organs", []),
            "confirmed_diseases": score_data.get("confirmed_diseases", []),
            "possible_organs": score_data.get("possible_organs", []),
            "possible_diseases": score_data.get("possible_diseases", []),
            "branches": list((score_data.get("branches", {}) or {}).values()),
        })

    # Re-rank the confirmation view using patient-supported evidence first.
    # Raw astrology score remains as a tie-breaker and is preserved as original_rank.
    summary.sort(
        key=lambda item: (
            item.get("support_score", 0),
            item.get("yes_strong", 0),
            item.get("yes_but", 0),
            -item.get("no_strong", 0),
            -item.get("no_but", 0),
            item.get("hitlist_score", 0),
            item.get("convergence", 0),
            -item.get("original_rank", 99),
        ),
        reverse=True
    )

    for new_rank, item in enumerate(summary, start=1):
        item["rank"] = new_rank

    return summary


# ── Main Engine Call ───────────────────────────────────────────

def run_combine(patient_id: str) -> dict:
    folder = f"patients/{patient_id}"

    # Verify files
    try:
        with open(f"{folder}/diagnosis.json") as f:
            diagnosis = json.load(f)
        with open(f"{folder}/chat_log.json") as f:
            chat_log = json.load(f)
        with open(f"{folder}/processed_logic.json") as f:
            logic = json.load(f)
    except FileNotFoundError as e:
        print(f"❌ Aborting aggregation: {e}")
        return {}

    disease_prob = calculate_disease_probability(diagnosis, chat_log)
    care_period  = calculate_care_period(diagnosis, chat_log, logic)
    food         = get_food_recommendations(diagnosis)
    doctor       = get_doctor_recommendation(disease_prob, diagnosis, chat_log)
    lifestyle    = get_lifestyle_recommendations(diagnosis)
    wellness     = get_wellness_suggestions(diagnosis)
    hitlist_summary = build_hitlist_confirmation_summary(logic, chat_log)

    # Top score calculation
    top_score = max([d["final_score"] for d in disease_prob]) if disease_prob else diagnosis.get("risk_score",{}).get("total",0)
    overall = get_risk_grade(top_score)

    final_output = {
        "patient_id":   patient_id,
        "generated_at": datetime.now().isoformat(),
        "disease_probability": disease_prob,
        "hitlist_confirmation": hitlist_summary,
        "overall_grade": {
            "score": round(top_score, 1),
            "grade": [g for g in RISK_GRADES if RISK_GRADES[g]["label"] == overall["label"]][0],
            **overall
        },
        "care_period": care_period,
        "food": food,
        "doctor": doctor,
        "lifestyle": lifestyle,
        "wellness": wellness,
        "raw_scores": {
            "step_a": diagnosis.get("risk_score", {}).get("step_a", 0),
            "step_b": diagnosis.get("risk_score", {}).get("step_b", 0),
            "step_c": diagnosis.get("risk_score", {}).get("step_c", 0),
            "total":  diagnosis.get("risk_score", {}).get("total", 0),
            "chat_turns": len(chat_log.get("turns", []))
        }
    }

    with open(f"{folder}/final_output.json", "w") as f:
        json.dump(final_output, f, indent=2)
    from chat_ai_context_builder import build_chat_ai_context
    build_chat_ai_context(patient_id, folder)

    print(f"✅ Aggregation complete for patient {patient_id}")
    return final_output


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--patient", required=True)
    args = parser.parse_args()
    
    import sys
    # Ensure current directory is in path for knowledge_base
    sys.path.append(os.getcwd())
    
    result = run_combine(args.patient)
    if result:
        print("\n--- AGGREGATION RESULT (SNEAK PEEK) ---")
        print(f"Overall Grade: {result['overall_grade']['label']}")
        print(f"Top Score:     {result['overall_grade']['score']}")
        print(f"See Doctor:    {result['doctor']['see_doctor']} ({result['doctor']['urgency']})")
        print(f"Care Until:    {result['care_period']['primary_care_until']}")
        print(f"----------------------------------------")
