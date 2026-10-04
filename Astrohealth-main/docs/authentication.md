# Authentication

IMPLEMENTED IN CODE.

Clerk is the only sign-in system. The legacy HTTP basic-auth username and password are not used.

## Browser

`static/session.js` loads `/public-config`, which returns only `clerkPublishableKey` and `frontendUrl`. The browser then loads Clerk's hosted script and sends `Authorization: Bearer <session JWT>` on same-origin API calls.

`CLERK_SECRET_KEY` is never included in that response.

## API

Protected routes use `authenticate_request()` from `clerk-backend-api` with:

- `accepts_token=["session_token"]`
- `authorized_parties` from `CLERK_AUTHORIZED_PARTIES`
- `jwt_key` from `CLERK_JWT_KEY` when set, which verifies the signature without a network call
- otherwise `CLERK_SECRET_KEY`, which makes the SDK fetch Clerk's JWKS
- `audience` from `CLERK_AUDIENCE` when that variable is set

The SDK checks the signature, expiry, not-before, audience (when configured), and authorized party (`azp`). The SDK does not check the issuer. `app_core/auth.py` rejects a token whose `iss` is not `CLERK_ISSUER`. When `CLERK_ISSUER` is empty, it is derived from `CLERK_PUBLISHABLE_KEY` (the Frontend API host embedded in that key). A token without `sub` is rejected.

The verified `sub` is the Clerk user id. The repository maps it to an internal user id. Body, query, and URL user ids are ignored.

## Authorized parties

Local: `http://localhost:8000`

Production: the HTTPS origin, for example `https://app.example.com`, set only in the environment. It is not hard-coded.

## Where to copy keys

Clerk Dashboard → API keys:

- Publishable key → `CLERK_PUBLISHABLE_KEY`
- Secret key → `CLERK_SECRET_KEY`
- JWT public key / PEM → `CLERK_JWT_KEY` (recommended so the API can verify tokens if Clerk's JWKS host is briefly unavailable)

Clerk Dashboard → the instance Frontend API host is the issuer, usually `https://<slug>.clerk.accounts.dev` in development. Put that in `CLERK_ISSUER` or leave it blank to derive it from the publishable key.

Add `http://localhost:8000` to the Clerk development instance's allowed origins. Do not add localhost to the production instance.

## Logout

Logout is Clerk's sign-out in the browser. The API does not keep a password session. After sign-out the browser stops sending a token, and protected routes return 401.

## Failure responses

| Condition | HTTP |
| --- | --- |
| Missing, expired, malformed, wrong signature, wrong issuer, wrong `azp`, wrong audience, missing `sub` | 401 |
| Authenticated caller asking for another user's patient | 404 |
| Authentication settings incomplete | 503 on the protected route and on `/ready` |
