# Architecture

## Status

IMPLEMENTED IN CODE: the application layout below.

MANUAL CLOUD CONFIGURATION REQUIRED: the Google Cloud project, Firestore production database, Compute Engine VM, IAM, Secret Manager, Cloudflare, and DNS.

NOT YET CONFIGURED: no production project, VM, or Cloudflare zone was created from this repository.

## What this application is

AstroMedica is a Flask application. It serves the existing HTML pages and runs the existing Vedic health algorithms. Prokerala supplies chart, birth, and dasha data. Gemini supplies the consultation chat. Clerk proves who the caller is. Firestore stores user-scoped inputs and results.

There is no separate frontend server and no worker process. The algorithms run inside the API request. A worker was not added because nothing in the legacy application consumed a queue.

## Request path

```
Browser
  -> Clerk (sign-in, session JWT)
  -> Flask on port 8000
       -> verify session JWT
       -> map Clerk user id to users/{internalUserId}
       -> Firestore
       -> Prokerala and Gemini when a chart or chat turn needs them
```

Production places Cloudflare in front of a Compute Engine VM that runs the same container. That proxy layer is documented in `cloudflare.md` and `google-cloud-vm.md`. It is not deployed by this repository.

## Local and production

The same Python code runs in both places. `APP_ENV`, origins, Clerk keys, and the Firestore target change.

| | Local | Production |
| --- | --- | --- |
| Process | Docker Compose `api` | Docker Compose production file on a VM |
| Datastore | Firestore emulator, `FIRESTORE_EMULATOR_HOST=firestore:8080` | Firestore in the GCP project, ADC on the VM |
| Auth | Clerk development instance | Clerk production instance |
| Edge | none | Cloudflare |

If `APP_ENV=development` and `FIRESTORE_EMULATOR_HOST` is empty, the API keeps data in memory and `/ready` returns 503. It does not fall back to a production Firestore database.

## Modules

- `server.py` — HTTP routes and the existing chart pipeline.
- `jataka_fetch.py`, `jataka_logic.py`, `rules.py`, and the other algorithm modules — unchanged mathematics.
- `chat_module.py` — consultation behavior.
- `app_core/` — settings, Clerk verification, authorization, Firestore repository, rate limits, and logging.

The package is named `app_core` so it does not shadow Python's standard-library `platform` module.

## Persistence boundary

Algorithms still read and write a patient directory on disk. That directory is a processing workspace. Firestore is the authorization and lineage record:

- `users/{internalUserId}`
- `users/{internalUserId}/inputs/{inputId}`
- `users/{internalUserId}/prokerala_results/{inputId}`
- `users/{internalUserId}/algorithm_results/{inputId}_{algorithm}`
- `users/{internalUserId}/combined_results/{inputId}_chart_summary` and `{inputId}_module_c`
- `users/{internalUserId}/chat_sessions/{sessionId}`
- `users/{internalUserId}/patients/{patientId}` ownership binding
- `users/{internalUserId}/audit_events/{eventId}`
- `clerk_index/{clerkUserId}` unique Clerk-to-internal mapping

Chart SVG is kept in the patient workspace for the existing results page. It is not written to Firestore.

## Prokerala

A chart still calls four endpoints because they return different data: planet position, chart SVG, birth details, and dasha periods. One planet-position response does not include the SVG or the dasha tree. The calls share one OAuth token, which is cached in the process.
