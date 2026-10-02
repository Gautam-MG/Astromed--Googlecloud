import asyncio

from app_core.errors import UpstreamError
from app_core.prokerala_token import ProkeralaTokenCache
from app_core.settings import issuer_from_publishable_key
from rules import apply_rule_1


def test_token_is_reused_until_expiry(monkeypatch):
    calls = {"count": 0}

    class Response:
        status_code = 200

        def json(self):
            return {"access_token": "token-1", "expires_in": 3600}

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, url, data):
            assert "client_secret" in data
            assert url.endswith("/token")
            calls["count"] += 1
            return Response()

    monkeypatch.setattr("app_core.prokerala_token.httpx.AsyncClient", Client)
    cache = ProkeralaTokenCache()
    first = asyncio.run(cache.get_token("id", "secret"))
    second = asyncio.run(cache.get_token("id", "secret"))
    assert first == second == "token-1"
    assert calls["count"] == 1


def test_missing_prokerala_credentials_do_not_call_network():
    cache = ProkeralaTokenCache()
    try:
        asyncio.run(cache.get_token("", ""))
    except UpstreamError as exc:
        assert exc.operation == "prokerala_not_configured"
    else:
        raise AssertionError("expected upstream error")


def test_rule1_sixth_house_occupant_is_rogkaraka():
    signs = [
        "Mesha", "Vrishabha", "Mithuna", "Karka", "Simha", "Kanya",
        "Tula", "Vrischika", "Dhanu", "Makara", "Kumbha", "Meena",
    ]
    chart = {
        "ascendant": {"house": 1, "name": "Mesha", "nakshatra": {"name": "Ashwini", "pada": 1}},
        "houses": [{"house": index + 1, "sign": {"name": sign}} for index, sign in enumerate(signs)],
        "planets": [{
            "name": "Saturn",
            "house": 6,
            "sign": {"name": "Kanya"},
            "degree": 10,
            "minutes": 0,
            "nakshatra": {"name": "Hasta", "pada": 2},
        }],
    }
    result = apply_rule_1(chart)
    assert result["sixth_house_number"] == 6
    assert result["rogkaraka_1"][0]["name"] == "Saturn"


def test_issuer_is_derived_from_publishable_key():
    import base64
    host = "example.clerk.accounts.dev$"
    encoded = base64.b64encode(host.encode()).decode().rstrip("=")
    assert issuer_from_publishable_key(f"pk_test_{encoded}") == "https://example.clerk.accounts.dev"


def test_firestore_rules_deny_client_access():
    rules = open("firestore.rules", encoding="utf-8").read()
    assert "allow read, write: if false" in rules
