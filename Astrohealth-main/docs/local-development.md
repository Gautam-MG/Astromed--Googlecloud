# Local development

The API and the HTML pages are the same process on port 8000. The Firestore emulator is port 8080 and is not exposed in production.

## 1. Required software

- Docker with Compose v2
- A Clerk development instance
- Prokerala client id and secret, and a Gemini API key, for live chart and chat calls

Python 3.11 is only required if you run pytest on the host.

## 2. Repository setup

```bash
cd Astrohealth-main
cp .env.example .env
```

## 3. Environment file

Edit `.env`. Leave secrets empty until you paste them. Do not commit `.env`.

`FIRESTORE_EMULATOR_HOST=firestore:8080` is correct for the API container. It is the Compose service name, not your laptop's localhost.

## 4. Clerk development configuration

In the Clerk Dashboard, open the development instance:

- Copy the publishable key into `CLERK_PUBLISHABLE_KEY`
- Copy the secret key into `CLERK_SECRET_KEY`
- Copy the JWT public key (PEM) into `CLERK_JWT_KEY`
- Set `CLERK_AUTHORIZED_PARTIES=http://localhost:8000`
- Add `http://localhost:8000` as an allowed origin on that development instance
- Leave localhost off the production instance

`CLERK_ISSUER` can stay empty. The API derives `https://<frontend-api-host>` from the publishable key.

## 5. Firestore emulator

The emulator starts with Compose. It stores data only in that container. It does not use production Firestore.

## 6. Docker startup

```bash
docker compose up --build
```

You should see `firestore` become healthy and `api` listen on port 8000. The first build installs Python dependencies and can take several minutes.

## 7. Frontend startup

No separate command. Open:

```text
http://localhost:8000/
```

## 8. API startup

The `api` service is the API. It starts with the same `docker compose up --build` command.

## 9. Worker

There is no worker. Do not start one.

## 10. Health checks

```bash
curl -sS -D - http://localhost:8000/health
curl -sS -D - http://localhost:8000/ready
```

`/health` returns HTTP 200 and `{"status":"ok"}` when the process is up.

`/ready` returns HTTP 200 when Clerk settings are present and the emulator answers. It returns HTTP 503 when either check fails. Neither check calls Prokerala.

## 11. Login and signup

Open `http://localhost:8000/`, choose Sign in, and create a user in the Clerk development instance. The account button in the header is Clerk's user button, which includes sign-out.

## 12. Authenticated API test

In the browser console after sign-in:

```javascript
const token = await window.Clerk.session.getToken();
const response = await fetch("/me/records", { headers: { Authorization: "Bearer " + token } });
console.log(response.status, await response.json());
```

Expect HTTP 200.

## 13. Firestore data verification

After a chart is generated, the emulator UI is not bundled. From another terminal:

```bash
curl -sS "http://127.0.0.1:8080/v1/projects/astromedica-local/databases/(default)/documents/clerk_index"
```

You should see a document whose id is the Clerk user id. Patient chart files for the algorithms are inside the `patient_data` Docker volume at `/app/patients`.

## 14. Prokerala test

Submit the birth form with a real city. The server geocodes the place in the browser through Nominatim, then `POST /generate-chart`. The API fetches planet position, chart SVG, birth details, and dasha periods. A second submit for the same person reuses the local chart cache and does not request a new OAuth token if the cached token is still valid.

## 15. Algorithm test

The chart response includes `rule1`, `dasha`, `complete_analysis`, and `diagnosis` from the existing modules. On the host, without Docker:

```bash
cd astrohealth-app-main
python -m pip install -r requirements-dev.txt
python -m pytest -q tests/test_prokerala_and_rules.py
```

## 16. Combined result test

Finish a consultation and let the page call `POST /combine-output`. The combined document id is `{input_id}_module_c` under `combined_results`. The chart pipeline also writes `{input_id}_chart_summary` as soon as the chart is generated.

## 17. Logout

Use the Clerk user button and sign out. `window.Clerk.user` becomes null.

## 18. Unauthorized request

```bash
curl -sS -D - -o /dev/null -X POST http://localhost:8000/generate-chart \
  -H 'Content-Type: application/json' \
  -d '{"name":"A","dob":"1990-01-01","birth_time":"08:00","lat":12.9,"lng":77.5,"gender":"Female"}'
```

Expect HTTP 401.

## 19. User isolation

Sign in as a second Clerk user in a private window. Copy a `patient_id` from the first user and request:

```text
GET /patient-data/<that-id>
```

Expect HTTP 404. The body says `Not found.` for both a missing id and another user's id.

## 20. Reset local Firestore data

```bash
docker compose down -v
docker compose up --build
```

`-v` deletes the Compose volumes, including emulator data, patient files, and the chart cache.

## 21. Stop everything

```bash
docker compose down
```

## 22. Troubleshooting

- `/ready` is 503: Clerk keys are empty or the emulator hostname is wrong. Inside Compose it must be `firestore:8080`.
- Chart returns 502: Prokerala credentials are missing or rejected. The response does not include the provider body.
- Sign-in button says configuration is missing: `CLERK_PUBLISHABLE_KEY` is empty and the container was not recreated after editing `.env`. Run `docker compose up --build` again.
- Port 8000 is in use: stop the other process or change the host mapping in `docker-compose.yml` and set `CLERK_AUTHORIZED_PARTIES` to that same origin.

## What was exercised in this workspace

Docker was not installed in the environment that produced this change, so `docker compose up` was not executed here. Host tests and a direct Firestore emulator process were run instead. See `testing.md`.
