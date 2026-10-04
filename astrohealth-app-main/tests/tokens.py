import os
import time

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PRIVATE_PEM = _key.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption(),
)
OTHER_PRIVATE_PEM = _other.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption(),
)
PUBLIC_PEM = _key.public_key().public_bytes(
    serialization.Encoding.PEM,
    serialization.PublicFormat.SubjectPublicKeyInfo,
).decode("utf-8")

ISSUER = "https://test.clerk.accounts.dev"
AUDIENCE = "astromedica-test"
PARTY = "http://localhost:8000"

os.environ["APP_ENV"] = "test"
os.environ["CLERK_JWT_KEY"] = PUBLIC_PEM
os.environ["CLERK_SECRET_KEY"] = "sk_test_local_only"
os.environ["CLERK_ISSUER"] = ISSUER
os.environ["CLERK_AUDIENCE"] = AUDIENCE
os.environ["CLERK_AUTHORIZED_PARTIES"] = PARTY
os.environ["ALLOWED_ORIGINS"] = PARTY
os.environ["FRONTEND_URL"] = PARTY
os.environ["API_URL"] = PARTY
os.environ["FIRESTORE_PROJECT_ID"] = os.environ.get("FIRESTORE_PROJECT_ID", "astromedica-test")
if os.environ.get("RUN_FIRESTORE_EMULATOR_TESTS") != "1":
    os.environ.pop("FIRESTORE_EMULATOR_HOST", None)


def make_token(
    sub="user_a",
    iss=ISSUER,
    aud=AUDIENCE,
    azp=PARTY,
    exp=None,
    nbf=None,
    private_key=PRIVATE_PEM,
    omit=(),
):
    now = int(time.time())
    payload = {
        "sub": sub,
        "iss": iss,
        "aud": aud,
        "azp": azp,
        "iat": now,
        "nbf": now - 5 if nbf is None else nbf,
        "exp": now + 600 if exp is None else exp,
        "sid": "sess_test",
    }
    for key in omit:
        payload.pop(key, None)
    return jwt.encode(payload, private_key, algorithm="RS256")


def auth_header(sub="user_a", **kwargs):
    return {"Authorization": f"Bearer {make_token(sub=sub, **kwargs)}"}
