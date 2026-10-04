# Manual setup checklist

## Cursor has done

- Application code on the legacy Flask and algorithm baseline
- Clerk session verification and authorized-party configuration
- Internal user ids and ownership checks
- Firestore repository, rules file, and emulator hostname
- Persistence for inputs, Prokerala summaries, algorithm outputs, combined results, and chat turns
- Prokerala token cache, timeouts, and transient retries
- Dockerfiles and Compose files for local and production
- Health and readiness routes, request ids, CORS, body limit, and process-local rate limits
- Automated tests in `astrohealth-app-main/tests`
- The documents in `docs/`

## You must do manually

- Create the Google Cloud project and billing
- Create the production Firestore database
- Create the Clerk production instance, allowed origin, and keys
- Create Secret Manager secrets and the VM service account IAM bindings
- Create the Compute Engine VM, firewall, and Docker host
- Put `/etc/astromedica.env` on the VM with mode 600
- Build and start `docker-compose.prod.yml`
- Install origin TLS and set Cloudflare to Full (strict)
- Create the DNS record, proxy, WAF, and edge rate limit
- Confirm a real signup, chart, Firestore document, and Prokerala call on that hostname
- Enable the Firestore backup schedule and restore it once in staging

## Not done because this environment cannot

- Sign in to your Clerk, Google Cloud, Cloudflare, Prokerala, or Gemini accounts
- Claim that production is deployed
