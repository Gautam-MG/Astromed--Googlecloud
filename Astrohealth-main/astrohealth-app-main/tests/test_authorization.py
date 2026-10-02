import json

from app_core.runtime import get_services
from tests.tokens import auth_header

CHART = {
    "name": "Asha Rao",
    "dob": "1990-01-15",
    "birth_time": "08:30",
    "lat": 12.9716,
    "lng": 77.5946,
    "birth_place": "Bengaluru",
    "gender": "Female",
    "user_id": "user_forged",
}


def _patch_chart_pipeline(monkeypatch):
    async def fake_fetch(**kwargs):
        patient_id = "001"
        folder = f"patients/{patient_id}"
        import os
        os.makedirs(folder, exist_ok=True)
        with open(f"{folder}/raw_chart.json", "w") as handle:
            json.dump({"name": kwargs["name"], "chart_key": kwargs["owner_id"]}, handle)
        return {
            "patient_id": patient_id,
            "planets": [],
            "houses": [],
            "ascendant": {"name": "Mesha"},
            "svg_raw": "<svg></svg>",
            "source": "test-fixture",
        }

    async def fake_positions(*_args, **_kwargs):
        return {"planets": []}

    def fake_logic(patient_id):
        data = {
            "rule1": {"rogkaraka_1": []},
            "dasha": {},
            "complete_analysis": {"most_probable": ["Headache"], "top_diseases": []},
        }
        with open(f"patients/{patient_id}/processed_logic.json", "w") as handle:
            json.dump(data, handle)
        return data

    monkeypatch.setattr("server.fetch_and_save", fake_fetch)
    monkeypatch.setattr("server.fetch_current_planetary_positions", fake_positions)
    monkeypatch.setattr("server.run_logic", fake_logic)
    monkeypatch.setattr("server.run_diagnose", lambda _patient_id: {"summary": "fixture"})
    monkeypatch.setattr("server.calculate_second_ascendant", lambda **_kwargs: {})
    monkeypatch.setattr("server.run_zone_analysis", lambda *_args, **_kwargs: {})
    monkeypatch.setattr("server.build_imp_rashi_distance_analysis", lambda *_args, **_kwargs: {})
    monkeypatch.setattr("server.build_birth_current_distance_analysis", lambda *_args, **_kwargs: {})
    monkeypatch.setattr("rules.apply_disease_filter", lambda *_args, **_kwargs: {})


def test_forged_body_user_id_is_ignored(client, monkeypatch):
    _patch_chart_pipeline(monkeypatch)
    response = client.post("/generate-chart", headers=auth_header("user_b"), json=CHART)
    assert response.status_code == 200
    body = response.get_json()
    services = get_services()
    owner = services.repository.get_or_create_user("user_b")
    forged = services.repository.get_or_create_user("user_forged")
    assert services.repository.owns_patient(owner["internal_user_id"], body["patient_id"])
    assert not services.repository.owns_patient(forged["internal_user_id"], body["patient_id"])
    stored = services.repository.get(owner["internal_user_id"], "inputs", body["input_id"])
    assert stored["profile"]["name"] == "Asha Rao"
    assert stored["owner_internal_user_id"] == owner["internal_user_id"]


def test_other_user_cannot_read_patient_by_url_or_query(client, monkeypatch):
    _patch_chart_pipeline(monkeypatch)
    created = client.post("/generate-chart", headers=auth_header("user_a"), json=CHART)
    patient_id = created.get_json()["patient_id"]
    denied = client.get(f"/patient-data/{patient_id}?user_id=user_a", headers=auth_header("user_b"))
    assert denied.status_code == 404
    allowed = client.get(f"/patient-data/{patient_id}?user_id=user_b", headers=auth_header("user_a"))
    assert allowed.status_code == 200


def test_unknown_patient_url_does_not_confirm_existence(client):
    response = client.get("/patient-data/999", headers=auth_header("user_a"))
    assert response.status_code == 404
    assert response.get_json()["error"] == "Not found."


def test_direct_repository_read_is_scoped_to_the_owner(client, monkeypatch):
    _patch_chart_pipeline(monkeypatch)
    created = client.post("/generate-chart", headers=auth_header("user_a"), json=CHART).get_json()
    services = get_services()
    owner = services.repository.get_or_create_user("user_a")
    other = services.repository.get_or_create_user("user_c")
    assert services.repository.get(other["internal_user_id"], "inputs", created["input_id"]) is None
    assert services.repository.get(owner["internal_user_id"], "prokerala_results", created["input_id"])
    algorithms = services.repository.get(
        owner["internal_user_id"],
        "algorithm_results",
        f"{created['input_id']}_rule1",
    )
    assert algorithms["input_id"] == created["input_id"]
    combined = services.repository.list_records(owner["internal_user_id"])["results"]
    assert combined
    assert "<svg" not in json.dumps(services.repository.get(owner["internal_user_id"], "prokerala_results", created["input_id"]))


def test_chat_session_is_not_shared(client):
    services = get_services()
    owner = services.repository.get_or_create_user("user_a")
    services.repository.bind_patient(owner["internal_user_id"], "001", "input-1")
    services.session_owners["sess_1"] = {"internal_user_id": owner["internal_user_id"], "patient_id": "001"}
    denied = client.post(
        "/send-message",
        headers=auth_header("user_b"),
        json={"session_id": "sess_1", "message": "hello", "user_id": "user_a"},
    )
    assert denied.status_code == 404


def test_path_style_patient_id_is_rejected(client):
    response = client.get("/patient-data/..%2F..%2Fetc", headers=auth_header())
    assert response.status_code in {400, 404}
