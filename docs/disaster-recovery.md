# Disaster recovery

NOT YET CONFIGURED. No backup schedule is active. The commands below are the procedure to put one in place.

## What would be backed up

Firestore is the authoritative user, input, and result store. Patient workspace files on the VM disk are a cache the algorithms need in order to redisplay a chart, including the SVG. Back up Firestore first. The disk volume is secondary and contains more personal data, so treat the export bucket as sensitive.

## Create an export bucket and schedule

```bash
gcloud storage buckets create gs://PROJECT_ID-firestore-backups --location=LOCATION --uniform-bucket-level-access
gcloud firestore backups schedules create \
  --database='(default)' \
  --retention=14w \
  --recurrence=daily
```

A daily schedule with 14 weeks of retention is the recommended starting point. It is not enabled until someone runs the command.

An on-demand export:

```bash
gcloud firestore export gs://PROJECT_ID-firestore-backups/manual-$(date -u +%Y%m%d) \
  --database='(default)'
```

The VM service account does not need permission to export. Grant `roles/datastore.importExportAdmin` to a break-glass operator account, not to the application service account.

## Restore

Restore into a new database or a maintenance window. Import replaces documents with the exported copies.

```bash
gcloud firestore import gs://PROJECT_ID-firestore-backups/PATH \
  --database='(default)'
```

## Limitations

- Exports do not include Clerk users. Those live in Clerk. Recreate the Clerk instance mapping by having users sign in; `clerk_index` is part of the Firestore export, so existing internal ids return when the same Clerk id signs in.
- Exports do not include the Prokerala token or in-memory chat sessions.
- The emulator is not a backup of production.
- This repository has not run an export or a restore.

## How to test recovery

Export a staging database, delete one test user document, import into a separate staging database, and read the document back with a script that uses that database's service account. Record the time the import took. Do this before calling the backup verified.
