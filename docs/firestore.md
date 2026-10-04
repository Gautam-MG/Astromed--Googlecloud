# Firestore

IMPLEMENTED IN CODE: repository, security rules file, emulator hostname handling.

MANUAL: creating the production database, indexes, and IAM.

NOT YET CONFIGURED: no production database was created.

## Decision

The browser does not use the Firestore client SDK. The API uses the Admin SDK. `firestore.rules` denies every client read and write:

```
allow read, write: if false;
```

Those rules are not a substitute for the API checks. The Admin SDK bypasses rules. User isolation is enforced in `app_core/repository.py` by reading and writing only under the verified internal user id.

## Local

`FIRESTORE_EMULATOR_HOST=firestore:8080` inside Compose, or `127.0.0.1:8080` if the API runs on the host. The project id for local data is `astromedica-local`. The emulator is not production.

Automated tests use an in-memory repository unless `RUN_FIRESTORE_EMULATOR_TESTS=1` and `FIRESTORE_EMULATOR_HOST` are set. Emulator tests do not prove production query, index, or transaction behavior.

## Production

The VM service account uses Application Default Credentials. Do not put a service-account JSON key in the image or the repository. When `FIRESTORE_EMULATOR_HOST` is set, the client uses anonymous credentials so a laptop does not need a service-account file and cannot silently use production credentials.

`/ready` calls a lightweight list of root collections. It does not call Prokerala or Gemini.

## Documents

Each stored record includes `owner_internal_user_id`, `created_at`, `updated_at`, `schema_version`, `source`, and lineage ids (`input_id`, `prokerala_result_id`, `algorithm_result_ids`) where they apply. Document ids for an input are a hash of the internal user id and the birth fingerprint, so a retry updates the same documents instead of creating duplicates.

Patient directories on disk are also keyed by that owner. Two Clerk users who submit the same birth details do not share a patient folder.

## What is not stored in Firestore

Generated PDF files, screenshots, and the Prokerala chart SVG. The results page still renders the SVG from the patient workspace file produced for that request.
