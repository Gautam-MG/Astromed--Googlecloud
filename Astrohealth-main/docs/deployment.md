# Deployment

MANUAL after the repository is on the VM. NOT YET CONFIGURED and not executed.

## 1. Project

```bash
gcloud config set project PROJECT_ID
gcloud services enable compute.googleapis.com firestore.googleapis.com secretmanager.googleapis.com
```

## 2. Firestore and IAM

Follow `google-cloud-vm.md` to create the native Firestore database and `astromedica-vm` with `roles/datastore.user` and `roles/secretmanager.secretAccessor`.

## 3. Secrets

```bash
printf '%s' 'PROKERALA_SECRET' | gcloud secrets create prokerala-client-secret --data-file=-
printf '%s' 'CLERK_SECRET' | gcloud secrets create clerk-secret-key --data-file=-
printf '%s' 'CLERK_PEM' | gcloud secrets create clerk-jwt-key --data-file=-
printf '%s' 'GEMINI_KEY' | gcloud secrets create gemini-api-key --data-file=-
```

Grant the VM service account `secretAccessor` on each secret. The commands above create the secret resources. They were not run here.

## 4. VM and firewall

Create the instance and firewall rules in `google-cloud-vm.md`.

## 5. Install Docker and fetch secrets

On the VM:

```bash
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-v2
umask 077
cat > /etc/astromedica.env <<EOF
APP_ENV=production
FRONTEND_URL=https://APP_HOSTNAME
API_URL=https://APP_HOSTNAME
ALLOWED_ORIGINS=https://APP_HOSTNAME
CLERK_AUTHORIZED_PARTIES=https://APP_HOSTNAME
CLERK_PUBLISHABLE_KEY=$(gcloud secrets versions access latest --secret=clerk-publishable-key)
CLERK_SECRET_KEY=$(gcloud secrets versions access latest --secret=clerk-secret-key)
CLERK_JWT_KEY=$(gcloud secrets versions access latest --secret=clerk-jwt-key)
CLERK_ISSUER=https://YOUR_INSTANCE.clerk.accounts.dev
FIRESTORE_PROJECT_ID=PROJECT_ID
PROKERALA_CLIENT_ID=$(gcloud secrets versions access latest --secret=prokerala-client-id)
PROKERALA_CLIENT_SECRET=$(gcloud secrets versions access latest --secret=prokerala-client-secret)
GEMINI_API_KEY=$(gcloud secrets versions access latest --secret=gemini-api-key)
TRUST_CLOUDFLARE=true
TRUST_PROXY=true
PORT=8000
EOF
sudo chmod 600 /etc/astromedica.env
```

Do not leave `FIRESTORE_EMULATOR_HOST` set in this file.

Create the publishable-key and client-id secrets the same way before running the substitutions. The publishable key is public by design; it is still loaded from the environment so the image stays free of environment-specific values.

## 6. Start the container

```bash
sudo docker compose -f docker-compose.prod.yml --env-file /etc/astromedica.env up -d --build
```

## 7. Host HTTPS

Install Caddy or nginx, proxy `https://APP_HOSTNAME` to `127.0.0.1:8000`, and install the origin certificate. Then set Cloudflare SSL/TLS to Full (strict).

## 8. Checks

```bash
curl -sS https://APP_HOSTNAME/health
curl -sS https://APP_HOSTNAME/ready
```

Sign in with a production Clerk user, submit a chart, and confirm a document under `users` in the Firestore console. Call Prokerala by submitting that chart. Read `sudo docker compose logs api` and confirm the lines are JSON without tokens or API keys.

## 9. Rollback

```bash
sudo docker compose -f docker-compose.prod.yml --env-file /etc/astromedica.env up -d --build
```

Point `APP_IMAGE` at the previous image tag if you publish images to Artifact Registry. This repository does not push images.
