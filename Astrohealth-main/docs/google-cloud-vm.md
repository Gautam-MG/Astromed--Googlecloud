# Google Cloud VM

MANUAL CLOUD CONFIGURATION REQUIRED. Nothing in this file has been applied to a project.

The production process is Docker on a Compute Engine VM. It is not Cloud Run, GKE, or Kubernetes.

## Project and APIs

```bash
gcloud config set project PROJECT_ID
gcloud services enable compute.googleapis.com firestore.googleapis.com secretmanager.googleapis.com iam.googleapis.com
```

## Firestore

```bash
gcloud firestore databases create --location=LOCATION --type=firestore-native
```

Pick a region and keep it. This command creates the production database, which is separate from the emulator.

## Service account

```bash
gcloud iam service-accounts create astromedica-vm --display-name="AstroMedica VM"
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:astromedica-vm@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/datastore.user"
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:astromedica-vm@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

Do not grant `roles/owner` or `roles/editor`. Do not download a JSON key. Attach the account to the VM:

```bash
gcloud compute instances create astromedica \
  --zone=ZONE \
  --machine-type=e2-standard-2 \
  --service-account=astromedica-vm@PROJECT_ID.iam.gserviceaccount.com \
  --scopes=https://www.googleapis.com/auth/cloud-platform \
  --image-family=debian-12 \
  --image-project=debian-cloud \
  --tags=astromedica-web
```

`cloud-platform` scope lets the attached account use IAM. The IAM roles above are what actually allow Firestore and Secret Manager.

## Firewall

```bash
gcloud compute firewall-rules create astromedica-ssh \
  --direction=INGRESS --action=ALLOW --rules=tcp:22 \
  --source-ranges=ADMIN_IP/32 --target-tags=astromedica-web

gcloud compute firewall-rules create astromedica-http \
  --direction=INGRESS --action=ALLOW --rules=tcp:80,tcp:443 \
  --source-ranges=CLOUDFLARE_IPV4,CLOUDFLARE_IPV6 --target-tags=astromedica-web
```

Replace the Cloudflare ranges with the current lists published by Cloudflare. Do not use `0.0.0.0/0` for the application port if Cloudflare is the intended edge.

| Port | Purpose | Source | Public |
| --- | --- | --- | --- |
| 22 | SSH | Your admin IP | Restricted |
| 80 | HTTP redirect to HTTPS on the origin | Cloudflare | No, if the source ranges are Cloudflare |
| 443 | HTTPS origin | Cloudflare | No, if the source ranges are Cloudflare |
| 8000 | API inside Docker | VM localhost, published to 443 by the host proxy | Not a public GCP firewall port |
| 8080 | Firestore emulator | Not used in production | No |
| 5432, 6379, 6333 | Removed. Postgres, Redis, and Qdrant are not part of this design | — | No |

Firestore has no VM firewall rule. Clients do not connect to it.

## Docker on the VM

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2
sudo usermod -aG docker "$USER"
```

Copy the repository to the VM with git. Do not copy `.env` from a laptop into a public gist. Create `/etc/astromedica.env` with mode 600 from Secret Manager (see `deployment.md`) and point Compose at it.

`deploy/vm-startup.sh` is a reference boot script. It is not installed on a VM.

## Origin TLS

NOT YET CONFIGURED. Terminate TLS in Caddy or nginx on the VM with a certificate Cloudflare will accept in Full (strict) mode, or use a Cloudflare Origin Certificate. The container itself listens on port 8000 without TLS.
