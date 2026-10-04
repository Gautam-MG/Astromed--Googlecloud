# Security

IMPLEMENTED IN CODE unless a paragraph says otherwise.

## Authentication and authorization

Reviewed against the current routes:

- Protected routes call Clerk `authenticate_request` and then require `iss` and `sub`.
- Session tokens only. Machine tokens and API keys are not accepted.
- The internal user id comes from `clerk_index`, not from the client.
- Patient and chat access checks the owner binding. A miss and a cross-user hit both return 404.
- `patient_id` and `session_id` must match a short safe pattern, which blocks path traversal into other patient directories.
- `/public-config` returns the publishable key only.

## Secrets

`config.py` no longer has a Prokerala client-id default. `.env` is gitignored. The image build excludes `.env`. Logs record route, status, duration, request id, and internal user id. They do not record tokens, Clerk secrets, Prokerala secrets, or raw provider bodies.

Production secret storage in Secret Manager is MANUAL and NOT YET CONFIGURED.

## Requests

- Explicit CORS origins from `ALLOWED_ORIGINS`. Credentialed wildcard CORS is not used. The browser sends a bearer token, and `supports_credentials` is false.
- `MAX_BODY_BYTES` defaults to 262144.
- Chart generation is limited to 6 requests per 5 minutes per internal user per process. Chat is 30 per 5 minutes. Reads are 120 per minute.
- This limit is not shared across Gunicorn workers or extra VMs.
- Prokerala GETs retry only on 429 and 5xx. A birth-detail lock stops two concurrent misses from calling Prokerala twice for the same birth fingerprint.
- Chart SVG and profile names are not written into the shared API cache.

## Proxy headers

`CF-Connecting-IP` is used only when `TRUST_CLOUDFLARE=true`. `X-Forwarded-For` is used only when `TRUST_PROXY=true`. Leave both false on a laptop. Set both true on the VM only when Cloudflare is the immediate caller. A client cannot spoof the rate-limit identity unless those flags are on and the VM port is reachable from the open internet.

## Containers

The API image runs as uid 10001, drops Linux capabilities, sets `no-new-privileges`, and uses a read-only root filesystem with a tmpfs on `/tmp`. Patient files and the chart cache are volumes. The emulator container is local-only and is not part of `docker-compose.prod.yml`.

The image was not built in this workspace because Docker was not installed. The Dockerfile is present and untested here.

## Firestore

Client rules deny all access. The API uses admin credentials and enforces ownership itself. Firestore is not given a public IP in the documented firewall.

## Review notes that remain

- Disk patient files are still required by the algorithms. Anyone with shell access on the VM can read them. Restrict SSH and the volume.
- The shared chart cache can still serve planetary data for a repeated birth fingerprint. Names are stripped before it is written.
- Rate limits and the Prokerala token cache are per process.
- `parse_excel.py` still depends on pandas. It is not on the request path.
- A live Clerk production instance, Cloudflare WAF, and origin certificate were not configured or penetration-tested.
