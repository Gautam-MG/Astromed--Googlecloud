# Testing

## Commands that exist

From `astrohealth-app-main`:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Firestore emulator integration, only when an emulator is already listening:

```bash
RUN_FIRESTORE_EMULATOR_TESTS=1 FIRESTORE_EMULATOR_HOST=127.0.0.1:8080 APP_ENV=test python -m pytest -q tests/test_firestore_emulator.py
```

Docker, from `Astrohealth-main`:

```bash
docker compose build
docker compose up --build
docker compose down
```

Health:

```bash
curl -sS -D - http://localhost:8000/health
curl -sS -D - http://localhost:8000/ready
```

There is no configured lint or format command. None was added that would fail the existing algorithm modules. There is no separate frontend test runner; the pages are static HTML.

## Automated coverage

- Valid session JWT, and rejection of missing, malformed, expired, wrongly signed, wrong-issuer, wrong-authorized-party, wrong-audience, and missing-subject tokens
- Forged `user_id` in a chart body
- Cross-user patient URL and query
- Repository reads scoped to the owner
- Chat session owned by another user
- Oversized body, malformed JSON, chart rate limit, security headers
- Prokerala token reuse and missing credentials
- `apply_rule_1` still marks a 6th-house occupant as rogkaraka 1
- Firestore rules file denies client access
- Emulator round trip when `RUN_FIRESTORE_EMULATOR_TESTS=1`

## Expectations

| Case | HTTP |
| --- | --- |
| Missing or invalid authentication | 401 |
| Another user's patient or chat session | 404 |
| Invalid chart input or malformed JSON | 400 |
| Body over `MAX_BODY_BYTES` | 413 |
| Too many chart requests in the process window | 429 |
| Prokerala or Gemini failure | 502 with a generic message |
| Process up | `/health` 200 |
| Auth configured and datastore reachable | `/ready` 200 |

Client bodies do not include stack traces or provider response text.

## Executed in this workspace

`python -m pytest -q` — 30 passed, 1 skipped (the skipped test is the emulator test when `RUN_FIRESTORE_EMULATOR_TESTS` is unset).

With the emulator listening on `127.0.0.1:8080`:

`RUN_FIRESTORE_EMULATOR_TESTS=1 FIRESTORE_EMULATOR_HOST=127.0.0.1:8080 FIRESTORE_PROJECT_ID=astromedica-local APP_ENV=test python -m pytest -q tests/test_firestore_emulator.py` — 1 passed.

A local process on port 8000, started with `APP_ENV=test`, returned HTTP 200 from `/health` and `/ready`, and HTTP 401 from `POST /generate-chart` with no token. `/ready` was 200 because test mode uses the in-memory store. Development without `FIRESTORE_EMULATOR_HOST` is covered by `test_development_without_emulator_is_not_ready` and returns not ready.

Chrome checked the landing page and results page at 390, 768, 1280, and 1440 pixel widths. `documentElement.scrollWidth` matched the viewport, so the page did not scroll sideways. The phone form accepted a name and date, and the menu button opened the navigation. A results page loaded from session storage showed the patient name. Docker Compose was not run: Docker is not installed in this workspace. A Clerk development signup was not run: no Clerk keys were available.

## End-to-end

The pytest chart test drives `POST /generate-chart` with the real route, a verified test JWT, and stand-ins for Prokerala and the heavy calculators, then checks Firestore-shaped records for the input, Prokerala summary, rule1 result, and combined summary.

A live browser signup was not run. This workspace has no Clerk development keys. Logout is covered by a follow-up request with no token, which returns 401.

## Production Firestore

Do not treat emulator or in-memory tests as proof of production indexes, transactions, or IAM. Before release, run one chart against a staging Firestore database with the VM service account and confirm the document paths in the console.
