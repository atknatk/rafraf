# JWT Key Rotation Runbook (T2.9)

> Operational procedure for rotating the JWT signing keys used by the RafRaf
> backend (`apps/backend/app/core/security.py`). Covers both the **HS256 →
> RS256 cutover** (one-time migration) and **routine RS256 keypair rotation**
> (recurring). Implemented by T2.9 (Faz 2 — production hardening).

## TL;DR

| Setting | Purpose |
|---|---|
| `JWT_ALGORITHM` | `RS256` (default after T2.9) |
| `JWT_PRIVATE_KEY_PATH` | PEM file used to **sign** new tokens |
| `JWT_PUBLIC_KEY_PATH` | PEM file used to **verify** RS256 tokens |
| `JWT_LEGACY_HS256_SECRET` | Old HS256 secret — **verify only** during grace |
| `JWT_LEGACY_GRACE_UNTIL` | UTC ISO-8601 deadline; HS256 tokens rejected after |
| `JWT_SECRET_KEY` | DEPRECATED — will be removed after the grace period |

The decoder always tries **RS256 first**. If RS256 fails AND the grace
period is still active AND a legacy HS256 secret is configured, it falls
back to HS256 verification. Outside the grace window, HS256 tokens are
rejected and logged as `legacy_hs256_token_rejected_post_grace`.

---

## 1. Generating an RSA keypair (dev)

```bash
bash infra/scripts/generate-jwt-keys.sh ./secrets
# → ./secrets/jwt_private.pem (chmod 600)
# → ./secrets/jwt_public.pem  (chmod 644)
```

The `secrets/` directory is git-ignored. Never commit `*.pem`.

---

## 2. HS256 → RS256 cutover (one-time)

Use this procedure once when migrating an existing HS256-only deployment to
RS256.

1. **Generate a fresh RSA keypair** (2048-bit RSA — see §1).
2. **Distribute the public key** to every backend pod / instance and any
   external verifier (CI, downstream services). For EKS:
   ```bash
   kubectl create secret generic jwt-keypair \
     --from-file=jwt_private.pem=./secrets/jwt_private.pem \
     --from-file=jwt_public.pem=./secrets/jwt_public.pem
   ```
   Mount as a file (NOT env vars). Project the keys at
   `/etc/rafraf/jwt_*.pem` and set `JWT_PRIVATE_KEY_PATH=/etc/rafraf/jwt_private.pem`,
   `JWT_PUBLIC_KEY_PATH=/etc/rafraf/jwt_public.pem`.
3. **Configure the grace period**. Pick a deadline at least as long as the
   longest-lived HS256 token still in circulation (typically `JWT_REFRESH_TOKEN_EXPIRE_DAYS`,
   default 7 days):
   ```
   JWT_LEGACY_HS256_SECRET=<the previous JWT_SECRET_KEY>
   JWT_LEGACY_GRACE_UNTIL=2026-08-01T00:00:00Z
   ```
4. **Set the algorithm**:
   ```
   JWT_ALGORITHM=RS256
   ```
5. **Deploy**. New tokens are now signed with RS256. Old HS256 tokens are
   still accepted for verification (logged as `legacy_hs256_token_accepted`).
6. **Wait out the grace period.** Monitor logs for
   `legacy_hs256_token_accepted` count — it should taper to zero as old
   tokens expire and clients refresh.
7. **After the cutover deadline**: confirm zero
   `legacy_hs256_token_accepted` events in the last 24h, then unset
   `JWT_LEGACY_HS256_SECRET` and remove the deprecated `JWT_SECRET_KEY` env
   var. Any HS256 tokens that arrive afterwards are rejected and logged as
   `legacy_hs256_token_rejected_post_grace`.

---

## 3. Routine RS256 keypair rotation

Rotate the RSA keypair on a regular cadence (e.g. every 90 days) or
immediately on suspected compromise.

1. **Generate the new keypair** offline:
   ```bash
   bash infra/scripts/generate-jwt-keys.sh ./secrets-new
   ```
2. **Publish the NEW public key** alongside the old one. (Currently the
   backend supports a single public key — for true overlap, run a brief
   `decode_token` extension that tries both. Until then, schedule the
   rotation during a low-traffic window and accept short-lived 401 churn
   for in-flight tokens.)
3. **Replace the private key** on all backend pods and restart so the
   `_load_pem` cache picks up the new file. For Kubernetes:
   ```bash
   kubectl create secret generic jwt-keypair \
     --from-file=jwt_private.pem=./secrets-new/jwt_private.pem \
     --from-file=jwt_public.pem=./secrets-new/jwt_public.pem \
     --dry-run=client -o yaml | kubectl apply -f -
   kubectl rollout restart deployment/rafraf-backend
   ```
4. **Wait for `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`** (default 15min) so any
   tokens signed under the old key naturally expire. Refresh tokens
   (default 7 days) will be re-issued under the new key on the next
   refresh.
5. **Destroy the old private key** (`shred -u ./secrets/jwt_private.pem`)
   once nothing depends on it.

---

## 4. Production key storage

| Environment | Storage |
|---|---|
| Dev (local) | `./secrets/jwt_*.pem` (git-ignored) |
| CI | GitHub Actions secrets, decoded into a temp file before tests |
| Staging | AWS Secrets Manager → mounted as a file via External Secrets Operator |
| Production (EKS) | AWS Secrets Manager → Kubernetes Secret → projected file |

Never set the **private** key in an env var or log it. The public key is
safe to publish (e.g. as a JWKS endpoint in a future iteration).

---

## 5. Observability

The decoder emits structured logs at every verification:

| Event | When | Action |
|---|---|---|
| `jwt_token_signed` (debug) | Token signed | n/a |
| `jwt_token_verified` (debug) | Token verified | n/a |
| `legacy_hs256_token_accepted` (warning) | HS256 token accepted during grace | Track migration progress |
| `legacy_hs256_token_rejected_post_grace` (warning) | HS256 token after deadline | Investigate stale clients |

Alert on a sustained spike in either of the two warnings.
