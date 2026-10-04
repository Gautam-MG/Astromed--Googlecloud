# Operations

IMPLEMENTED: `/health`, `/ready`, JSON request logs, Docker healthcheck command.

NOT YET CONFIGURED: uptime checks, log sinks, paging, and a production VM.

## Health

`GET /health` returns 200 when the process can respond. Use it for the Docker healthcheck and a load balancer. It does not call Firestore or Prokerala.

`GET /ready` returns 200 only when authentication settings are complete and the datastore check succeeds. In production that check is a Firestore list of root collections using the VM service account. In development it requires `FIRESTORE_EMULATOR_HOST`.

## Logs

Stdout is one JSON object per line: timestamp, level, message, request id, route, status, duration, and internal user id when the caller was authenticated. Ship this stream with the VM's logging agent. Do not raise the log level in a way that prints request bodies.

## Restart

```bash
sudo docker compose -f docker-compose.prod.yml --env-file /etc/astromedica.env restart api
```

Gunicorn stops on SIGTERM with a 30 second grace period (`gunicorn.conf.py`). In-memory chat sessions and the Prokerala token cache are empty after a restart. Chat sessions that were persisted can be read from Firestore, but the live conversation model is still the in-memory store, so an in-progress chat must be started again after a restart. Chart inputs and results remain in Firestore. Patient workspace files remain on the Docker volume.

## Limits

Two Gunicorn workers is the default (`WEB_CONCURRENCY`). Each worker has its own rate limit and token cache. Chart requests can run for up to the Gunicorn timeout of 120 seconds because Prokerala and the local calculators are synchronous.

## Backup drill

Follow `disaster-recovery.md`. A backup that has not been restored is not verified. None has been restored here.
