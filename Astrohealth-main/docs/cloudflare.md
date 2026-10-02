# Cloudflare

MANUAL CLOUD CONFIGURATION REQUIRED. NOT YET CONFIGURED.

Cloudflare does not replace Clerk or the API's ownership checks.

## DNS

Create an A or AAAA record for the application hostname pointing at the VM's public IP. Proxy it (orange cloud).

## TLS

Use Full (strict) only after the origin presents a valid certificate (a public certificate or a Cloudflare Origin Certificate). Flexible mode is not the target. Authenticated origin pull is optional and not configured here.

## WAF and rate limits

Enable the Cloudflare WAF managed ruleset on the zone. Add a rate-limit rule for `POST /generate-chart` and `POST /send-message` at the edge. The application also rate-limits inside each Gunicorn process. The edge limit is the one that covers every worker.

## Headers the application trusts

Set `TRUST_CLOUDFLARE=true` and `TRUST_PROXY=true` only on the VM. The API then uses `CF-Connecting-IP` for the client address. It ignores `X-Forwarded-For` unless `TRUST_PROXY=true`.

Do not open the VM's HTTP port to the whole internet, or a client can bypass Cloudflare and, with those flags on, spoof `CF-Connecting-IP`.

## What Cloudflare is not doing in this repository

No zone id, API token, or WAF rule is stored in git. There is no Terraform stack. The checklist in `manual-setup-checklist.md` is the operator list.
