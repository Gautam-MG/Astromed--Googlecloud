import json

from tests.tokens import PARTY, auth_header, make_token

CHART = {
    "name": "Asha Rao",
    "dob": "1990-01-15",
    "birth_time": "08:30",
    "lat": 12.9716,
    "lng": 77.5946,
    "birth_place": "Bengaluru",
    "gender": "Female",
}


def test_missing_token_is_rejected(client):
    response = client.post("/generate-chart", json=CHART)
    assert response.status_code == 401
    assert "secret" not in response.get_data(as_text=True).lower()


def test_malformed_token_is_rejected(client):
    response = client.get("/me/records", headers={"Authorization": "Bearer not-a-jwt"})
    assert response.status_code == 401


def test_expired_token_is_rejected(client):
    import time
    token = make_token(exp=int(time.time()) - 120)
    response = client.get("/me/records", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_invalid_signature_is_rejected(client):
    from tests.tokens import OTHER_PRIVATE_PEM
    token = make_token(private_key=OTHER_PRIVATE_PEM)
    response = client.get("/me/records", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_wrong_issuer_is_rejected(client):
    token = make_token(iss="https://evil.example")
    response = client.get("/me/records", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_wrong_authorized_party_is_rejected(client):
    token = make_token(azp="https://attacker.example")
    response = client.get("/me/records", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_wrong_audience_is_rejected(client):
    token = make_token(aud="some-other-app")
    response = client.get("/me/records", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_missing_subject_is_rejected(client):
    token = make_token(omit=("sub",))
    response = client.get("/me/records", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_valid_token_can_read_own_records(client):
    response = client.get("/me/records", headers=auth_header())
    assert response.status_code == 200
    assert response.get_json()["success"] is True


def test_logout_means_the_next_request_without_a_token_is_rejected(client):
    assert client.get("/me/records", headers=auth_header()).status_code == 200
    assert client.get("/me/records").status_code == 401


def test_public_config_does_not_expose_secrets(client):
    payload = client.get("/public-config").get_json()
    encoded = json.dumps(payload)
    assert "sk_test" not in encoded
    assert "CLERK_SECRET" not in encoded
    assert "clerkPublishableKey" in payload


def test_authorized_party_constant_is_local_origin():
    assert PARTY.startswith("http://localhost:")
