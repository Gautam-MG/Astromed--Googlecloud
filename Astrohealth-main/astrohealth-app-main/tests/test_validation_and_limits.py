from app_core.errors import RequestValidationError, UpstreamError
from app_core.validation import parse_chart_input
from tests.tokens import auth_header


def test_chart_input_requires_real_coordinates():
    try:
        parse_chart_input({"name": "A", "dob": "1990-01-01", "birth_time": "01:00", "lat": 0, "lng": 0})
    except RequestValidationError as exc:
        assert "lat" in exc.message
    else:
        raise AssertionError("expected validation error")


def test_malformed_json_is_rejected(client):
    response = client.post(
        "/generate-chart",
        data="{not-json",
        headers={**auth_header(), "Content-Type": "application/json"},
    )
    assert response.status_code == 400
    assert "Traceback" not in response.get_data(as_text=True)


def test_oversized_body_is_rejected(client):
    response = client.post(
        "/generate-chart",
        data="{" + ("x" * 400000),
        headers={**auth_header(), "Content-Type": "application/json"},
    )
    assert response.status_code == 413


def test_chart_rate_limit(client, monkeypatch):
    async def fail_fast(**_kwargs):
        raise UpstreamError("prokerala")

    monkeypatch.setattr("server.fetch_and_save", fail_fast)
    headers = auth_header("user_rate")
    body = {
        "name": "Rate Limit",
        "dob": "1988-04-14",
        "birth_time": "06:42",
        "lat": 19.07,
        "lng": 72.87,
        "gender": "Male",
    }
    statuses = [client.post("/generate-chart", headers=headers, json=body).status_code for _ in range(7)]
    assert statuses[-1] == 429
    assert 502 in statuses


def test_security_headers_and_request_id(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-Request-ID"]


def test_ready_in_test_mode(client):
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.get_json()["checks"]["authentication"] == "ok"


def test_development_without_emulator_is_not_ready(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    from app_core.runtime import Services
    from app_core.settings import load_settings

    ready, checks = Services(load_settings()).ready()
    assert ready is False
    assert checks["datastore"] == "not_ready"
