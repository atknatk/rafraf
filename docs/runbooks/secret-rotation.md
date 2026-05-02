# Secret Rotation Runbook (T3.8)

> Rotation procedures for **all** production secrets used by the RafRaf
> system. Covers routine cadence-driven rotation and emergency
> compromise-driven rotation. Source of truth for SRE + on-call.
>
> **Cross-references:**
> - [`docs/10_Production_Pivot_Spec.md`](../10_Production_Pivot_Spec.md) §7.4 (Security)
> - [`docs/12_Action_Plan_Tasks.md`](../12_Action_Plan_Tasks.md) §6 T3.8
> - [`docs/runbooks/jwt-key-rotation.md`](./jwt-key-rotation.md) — full JWT keypair detail (T2.9)
> - [`docs/runbooks/disaster-recovery.md`](./disaster-recovery.md) §3.4 — JWT compromise DR-specific path
> - [`docs/runbooks/deploy.md`](./deploy.md) — coordinate rotations with deploy windows

---

## 1. Secret inventory

The table below is the **complete** list of production secrets. If you add
a new secret, add a row here AND a §3.x specific procedure.

| # | Secret | Storage location | Rotation frequency | Owner | Specific procedure |
|---|---|---|---|---|---|
| 1 | JWT private key (`JWT_PRIVATE_KEY_PATH`) | AWS Secrets Manager `rafraf/jwt-keys` → ESO → K8s `Secret` `jwt-keypair` → projected file `/etc/rafraf/jwt_private.pem` | **90 days** OR on compromise | SRE | §3.1 + [`jwt-key-rotation.md`](./jwt-key-rotation.md) |
| 2 | JWT public key (`JWT_PUBLIC_KEY_PATH`) | Same as above (paired with private) | Paired with #1 | SRE | §3.1 |
| 3 | `JWT_LEGACY_HS256_SECRET` (HS256 grace) | AWS Secrets Manager `rafraf/jwt-legacy-hs256` | One-time (unset after grace expiry, T2.9 cutover) | SRE | §3.1 (cutover only) |
| 4 | `DATABASE_URL` password | AWS Secrets Manager `rafraf/database-url` (full URL form) | **180 days** | SRE | §3.2 |
| 5 | `REDIS_URL` password | AWS Secrets Manager `rafraf/redis-url` | **180 days** (only if AUTH enabled — ElastiCache token-auth path) | SRE | §3.3 |
| 6 | `ANTHROPIC_API_KEY` (V1.1+ fallback) | AWS Secrets Manager `rafraf/anthropic-api-key` | **Yearly** + on personnel change (departing engineer) | Platform lead | §3.4 |
| 7 | APNs auth key (`.p8`) | AWS Secrets Manager `rafraf/apns-key` (binary blob, JSON `{key_id, team_id, p8}`) | **Yearly** (Apple recommendation; keys do not expire but rotation hygiene) | iOS lead | §3.5 |
| 8 | AWS access keys (programmatic) | **N/A** in production — pods authenticate via IRSA (IAM Roles for Service Accounts). Only CI uses long-lived keys via OIDC, no static secrets stored | N/A (IRSA) / 90 days (CI OIDC token rotated automatically) | Platform lead | §3.6 |
| 9 | GitHub Personal Access Token (PAT) — image pull from GHCR | K8s `Secret` `ghcr-pull-secret` (`dockerconfigjson` type), source = AWS Secrets Manager `rafraf/ghcr-pull-pat` | **90 days** | SRE | §3.7 |
| 10 | Bridge `pairing_token` (per-bridge bootstrap) | Generated server-side at first pair, stored in Postgres `bridges.pairing_token_hash` (bcrypt) + delivered to bridge once via signed URL | **Manual** (per-bridge, on suspected leak OR engineer offboarding OR new device) | Bridge owner | §3.8 |
| 11 | `BRIDGE_AUTH_TOKEN` (long-lived bridge → backend WS auth) | Issued per-bridge after pairing; stored in bridge keychain + Postgres `bridges.auth_token_hash` | **365 days** (rotate via re-pair flow) | Bridge owner | §3.8 |
| 12 | `dockerconfigjson` (alias for #9 K8s representation) | K8s `Secret` `ghcr-pull-secret` mounted by `imagePullSecrets` | Paired with #9 | SRE | §3.7 |

> **Why no row for OAuth client secrets?** Apple Sign In uses the team's
> sign-in-with-apple key (covered by APNs `.p8` rotation if shared, otherwise
> separately tracked under `rafraf/sign-in-apple-key`). Add a row here when
> we add a third-party OAuth provider.

---

## 2. General rotation procedure

Every secret rotation follows the same five-phase shape; per-secret
specifics are in §3.x.

```
1. Generate new secret (offline, local machine, never typed in plain logs)
2. Store in AWS Secrets Manager (new version)
3. ESO (External Secrets Operator) refreshes K8s Secret on next reconcile
   (default: 1h) — force with `kubectl annotate externalsecret ... force-sync=$(date +%s)`
4. Backend pods pick up the new secret on next restart
   (kubectl rollout restart deploy/rafraf-backend -n rafraf)
5. Verify, then revoke / shred the OLD secret AFTER grace window
```

### 2.1 Grace window guidance

Some secrets have natural overlap windows (e.g., DB password — accept BOTH
old and new for 5 min while rolling restart drains in-flight connections).
Others are atomic (e.g., GHCR PAT — old is revoked instantly the moment new
is in place).

| Secret type | Default grace | Why |
|---|---|---|
| JWT keys | 7 days (= refresh-token max age) | Tokens signed under old key must continue to verify until they naturally expire |
| DB password | 5 min | Pool connections drain |
| Redis password | 5 min | Pool connections drain |
| Anthropic API key | None — old key revoked at AWS step | Bridge restart picks up new instantly |
| APNs `.p8` | 24 h | Apple device tokens may already be in flight |
| GHCR PAT | None — atomic | Pull happens at pod start; old PAT can be revoked the moment new K8s Secret exists |
| Bridge `pairing_token` | 1 h | Tester needs time to re-pair |

### 2.2 Audit log

Every rotation **must** be logged in `infra/audit/rotations.log` (gitops
repo, append-only, signed commits). Format:

```
2026-05-02T14:33:00Z | secret=rafraf/jwt-keys | actor=<github-handle> | reason=routine-90day | next-due=2026-08-02
```

Run via:

```bash
cd <gitops-repo>
cat <<EOF >> infra/audit/rotations.log
$(date -u +%Y-%m-%dT%H:%M:%SZ) | secret=<secret-arn> | actor=$(git config user.email) | reason=<routine|compromise|offboarding> | next-due=<YYYY-MM-DD>
EOF
git add infra/audit/rotations.log
git commit -S -m "audit(rotation): rotate <secret> [reason]"
git push
```

---

## 3. Per-secret specifics

### 3.1 JWT keypair (RS256)

> **For full procedure** see [`jwt-key-rotation.md`](./jwt-key-rotation.md).
> The summary below is for muscle memory.

```bash
# 1. Generate new keypair offline
bash infra/scripts/generate-jwt-keys.sh ./secrets-new
# → ./secrets-new/jwt_private.pem (chmod 600)
# → ./secrets-new/jwt_public.pem  (chmod 644)

# 2. Push to AWS Secrets Manager
aws secretsmanager update-secret \
  --secret-id rafraf/jwt-keys \
  --secret-string "$(jq -n \
    --arg priv "$(cat ./secrets-new/jwt_private.pem)" \
    --arg pub  "$(cat ./secrets-new/jwt_public.pem)" \
    '{private: $priv, public: $pub}')"

# 3. Force ESO sync
kubectl annotate externalsecret rafraf-secrets force-sync=$(date +%s) -n rafraf --overwrite

# 4. Rolling restart
kubectl rollout restart deploy/rafraf-backend -n rafraf
kubectl rollout status deploy/rafraf-backend -n rafraf --timeout=5m

# 5. Verify
TOKEN=$(curl -sf -X POST https://backend.rafraf.app/api/v1/auth/apple ... | jq -r '.access_token')
# Decode the header — alg should be RS256, kid should be the new key id (if you embed kid)
echo "$TOKEN" | cut -d. -f1 | base64 -d 2>/dev/null | jq .

# 6. Wait JWT_REFRESH_TOKEN_EXPIRE_DAYS (7d default), then shred old key
shred -u ./secrets/jwt_private.pem
```

For **emergency** post-compromise rotation, see
[`disaster-recovery.md`](./disaster-recovery.md) §3.4 — different
sequencing (immediate revocation of grace HS256 tokens).

### 3.2 `DATABASE_URL` password

```bash
# 1. Generate new password
NEW_PW=$(openssl rand -base64 32 | tr -d '\n=' | head -c 40)

# 2. Apply to RDS instance (Postgres ALTER USER)
PGHOST=<rds-endpoint> PGUSER=rafraf_admin PGPASSWORD=<admin-pw> \
  psql -d postgres -c "ALTER USER rafraf WITH PASSWORD '${NEW_PW}';"

# 3. Build new URL and push to Secrets Manager
NEW_URL="postgresql+asyncpg://rafraf:${NEW_PW}@<rds-endpoint>:5432/rafraf"
aws secretsmanager update-secret \
  --secret-id rafraf/database-url \
  --secret-string "$NEW_URL"

# 4. Force ESO sync + rolling restart
kubectl annotate externalsecret rafraf-secrets force-sync=$(date +%s) -n rafraf --overwrite
kubectl rollout restart deploy/rafraf-backend -n rafraf
kubectl rollout status deploy/rafraf-backend -n rafraf --timeout=5m

# 5. Verify
curl -sf https://backend.rafraf.app/ready  # expect 200 with {"db":"ok",...}

# 6. (No grace window cleanup — old password is dead the moment ALTER USER ran)
```

> **Note:** SQLAlchemy connection pool may hold connections opened with the
> old password. The rolling restart in step 4 closes them. Do NOT skip the
> rollout restart even though `/ready` may transiently show OK from
> not-yet-restarted pods.

### 3.3 `REDIS_URL` password

```bash
# Production: ElastiCache token-auth (AUTH command)
NEW_PW=$(openssl rand -base64 32 | tr -d '\n=' | head -c 40)

# 1. Modify ElastiCache cluster auth token
aws elasticache modify-replication-group \
  --replication-group-id rafraf-redis-prod \
  --auth-token "$NEW_PW" \
  --auth-token-update-strategy ROTATE \
  --apply-immediately
# ROTATE strategy accepts BOTH old + new for ~5 min — perfect grace window.

# 2. Wait for "available" status
aws elasticache wait replication-group-available --replication-group-id rafraf-redis-prod

# 3. Build new URL + Secrets Manager
NEW_URL="rediss://:${NEW_PW}@<redis-primary-endpoint>:6379/0"
aws secretsmanager update-secret \
  --secret-id rafraf/redis-url \
  --secret-string "$NEW_URL"

# 4. Sync + rolling restart
kubectl annotate externalsecret rafraf-secrets force-sync=$(date +%s) -n rafraf --overwrite
kubectl rollout restart deploy/rafraf-backend -n rafraf

# 5. Once all pods restarted, finalize the rotation (drops the old token)
aws elasticache modify-replication-group \
  --replication-group-id rafraf-redis-prod \
  --auth-token "$NEW_PW" \
  --auth-token-update-strategy SET \
  --apply-immediately

# 6. Verify
curl -sf https://backend.rafraf.app/ready  # expect 200 with {...,"redis":"ok"}
```

> **Self-hosted Redis (V1 Mac/VPS):** edit `redis.conf` `requirepass`,
> `redis-cli CONFIG SET requirepass "$NEW_PW"`, then update env, restart
> backend. No ROTATE strategy — brief reconnect storm is acceptable.

### 3.4 `ANTHROPIC_API_KEY` (fallback for V1.1+)

> **Only relevant if** the bridge is configured to fall back to API-key
> mode (rare — production uses Claude subscription via subprocess on Mac).

```bash
# 1. Create new key in Anthropic console (https://console.anthropic.com/)
#    Copy the value (only shown once!).

# 2. Push to Secrets Manager
aws secretsmanager update-secret \
  --secret-id rafraf/anthropic-api-key \
  --secret-string '{"api_key":"sk-ant-api03-<NEW>"}'

# 3. Sync + rolling restart (only bridge needs this; backend doesn't hold
#    the key in V1)
# For Mac bridge:
launchctl unload ~/Library/LaunchAgents/com.rafraf.bridge.plist
# (bridge re-reads keychain / config on next launch)
launchctl load ~/Library/LaunchAgents/com.rafraf.bridge.plist

# 4. Verify
curl -sf http://localhost:9090/healthz  # bridge healthz; expect "claude_api_key_configured":true

# 5. Revoke old key in Anthropic console
```

**Personnel-change trigger:** when an engineer with knowledge of (or
console access to) the production Anthropic key leaves the team, rotate
this key within 24 h regardless of the calendar schedule.

### 3.5 APNs `.p8` auth key

```bash
# 1. In Apple Developer portal:
#    Certificates, IDs & Profiles → Keys → "+" → enable APNs → Create
#    Download the .p8 (only chance to download — store securely)
#    Note key_id (10-char) and your team_id

# 2. Push to Secrets Manager
aws secretsmanager update-secret \
  --secret-id rafraf/apns-key \
  --secret-string "$(jq -n \
    --arg key_id "<NEW_KEY_ID>" \
    --arg team_id "VT3X56P4ZL" \
    --arg p8 "$(cat ~/Downloads/AuthKey_<NEW_KEY_ID>.p8)" \
    '{key_id: $key_id, team_id: $team_id, p8: $p8}')"

# 3. Sync + rolling restart
kubectl annotate externalsecret rafraf-secrets force-sync=$(date +%s) -n rafraf --overwrite
kubectl rollout restart deploy/rafraf-backend -n rafraf

# 4. Send a test push to one device (use a TestFlight build)
curl -sf -X POST https://backend.rafraf.app/api/v1/notifications/test \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"device_token":"<test-device-token>"}'
# Verify the push lands.

# 5. After 24 h grace (legacy in-flight pushes drain), revoke old key in
#    Apple Developer portal.

# 6. Securely shred the local .p8 file
shred -u ~/Downloads/AuthKey_<NEW_KEY_ID>.p8
```

### 3.6 AWS access keys (IRSA, not rotation)

Production pods use **IAM Roles for Service Accounts (IRSA)**. The pod
service account is mapped to an IAM role; AWS SDK uses the role via the
EKS OIDC provider, with credentials rotated automatically every 1 h. **No
static AWS access key exists** for the backend pod.

For CI (GitHub Actions), the `aws-actions/configure-aws-credentials@v4`
action uses GitHub's OIDC provider against the role
`arn:aws:iam::<account>:role/rafraf-ci-deploy`. Token lifetime is 1 h per
job; no rotation procedure needed.

If a long-lived access key is ever introduced (migration, special tool),
add a row to §1 and a procedure here. Default policy: **don't**.

### 3.7 GitHub PAT for GHCR pull

```bash
# 1. Create a new fine-grained PAT in GitHub
#    https://github.com/settings/tokens?type=beta
#    Repository access: only `atknatk/rafraf`
#    Permissions: read:packages
#    Expiration: 90 days
#    Copy the token (only shown once)

# 2. Build the dockerconfigjson + push to Secrets Manager
NEW_PAT="ghp_<NEW>"
DOCKERCONFIG=$(echo -n "atknatk:${NEW_PAT}" | base64)
DOCKERCONFIGJSON=$(jq -n --arg auth "$DOCKERCONFIG" '{
  "auths": {
    "ghcr.io": {
      "auth": $auth
    }
  }
}')
aws secretsmanager update-secret \
  --secret-id rafraf/ghcr-pull-pat \
  --secret-string "$DOCKERCONFIGJSON"

# 3. Sync ESO (creates K8s Secret of type kubernetes.io/dockerconfigjson)
kubectl annotate externalsecret ghcr-pull-secret force-sync=$(date +%s) -n rafraf --overwrite

# 4. Verify the new secret is in place
kubectl get secret ghcr-pull-secret -n rafraf -o jsonpath='{.data.\.dockerconfigjson}' | base64 -d | jq .

# 5. Rolling restart so new pods exercise the pull
kubectl rollout restart deploy/rafraf-backend -n rafraf
# (existing pods don't re-pull until they restart, so the rotation is silent
#  unless you force the restart. Some teams skip the restart and let the
#  next deploy validate the pull.)

# 6. Revoke the old PAT in GitHub immediately (no grace; pulls happen at
#    pod start, and step 4 confirmed the new one works before this step)
gh auth refresh   # only if revoking your own user PAT
# Or via UI: https://github.com/settings/tokens
```

### 3.8 Bridge pairing_token + BRIDGE_AUTH_TOKEN

Bridges authenticate to the backend in two phases:

1. **Bootstrap pair**: short-lived `pairing_token` issued by backend after
   the user enters a 6-digit code in iOS Settings; valid 1 h.
2. **Long-lived auth**: bridge exchanges `pairing_token` for a
   `BRIDGE_AUTH_TOKEN` (per-bridge, 365-day TTL) used in subsequent WS
   handshakes.

To rotate a single bridge's auth token (e.g., user reports "my bridge
disconnected and won't recover"):

```bash
# 1. Revoke the existing bridge record (server-side)
psql "$DATABASE_URL" -c "
  UPDATE bridges
  SET status = 'revoked', auth_token_hash = NULL, revoked_at = NOW()
  WHERE id = '<bridge-uuid>';"

# 2. User opens iOS app → Settings → Bridge → "Re-pair" → 6-digit code
#    appears in iOS, user types into bridge config UI on Mac
#    (or `rafraf-bridge pair --code 123456`)

# 3. Bridge calls /api/v1/bridges/pair with the code, receives a new
#    BRIDGE_AUTH_TOKEN, stores it in Mac keychain
#    (com.rafraf.bridge.auth)

# 4. Verify
curl -sf https://backend.rafraf.app/api/v1/bridges \
  -H "Authorization: Bearer $TOKEN" | jq '.[] | select(.id=="<bridge-uuid>")'
# Status should be "active", last_seen recent.
```

For **mass rotation** (e.g., suspected protocol-level leak):

```bash
# All bridges revoked; users will be prompted to re-pair.
psql "$DATABASE_URL" -c "
  UPDATE bridges
  SET status = 'revoked', auth_token_hash = NULL, revoked_at = NOW()
  WHERE status = 'active';"

# Push notification to all users explaining the re-pair requirement.
curl -sf -X POST https://backend.rafraf.app/api/v1/notifications/broadcast \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"category":"bridge_repair_required","title":"Bridge re-pair required","body":"Open Settings → Bridge to re-pair."}'
```

---

## 4. Emergency rotation (compromise)

> Use when a secret is **known or suspected** to be compromised: pushed to
> a public repo (GitHub secret-scanning alert), screen-shared on a stream,
> in an error log uploaded to a third-party service, or carried by a
> departing employee under hostile circumstances.

### 4.1 Decision matrix

| Signal | Severity | First action |
|---|---|---|
| GitHub secret-scan PUSH alert | P0 | Rotate immediately (this section) + git history rewrite (BFG Repo-Cleaner) |
| Anomalous JWT verification spike (`jwt_verify_errors_total` rate > 50/min — currently planned, not yet emitted) | P1 | §3.1 + investigate logs |
| Anomalous Anthropic API spend (`claude_total_cost_usd_total` rate > $50/h) | P1 | §3.4 + check key usage in Anthropic console |
| Anomalous GHCR pull pattern (unknown IPs) | P2 | §3.7 + audit GitHub repo access |
| Departing employee (hostile) | P0 | Rotate ALL secrets they had access to within 1 h of departure |
| Departing employee (amicable, normal offboarding) | P3 | Schedule rotation within 7 days; remove their console access first |
| Bridge `auth_token` brute-force attempt (per-bridge `bridge_auth_failed_total` spike — planned) | P2 | §3.8 single-bridge revoke + IP block |

### 4.2 Compromise response steps

1. **Page on-call.** P0/P1 → PagerDuty `rafraf-prod`. P2 → Slack
   `#rafraf-incidents`.
2. **Open the incident channel** in Slack: `/incident open <slug>`.
3. **Identify scope.** Which secret? Which environments? Last known good
   timestamp?
4. **Rotate per §3.x.** Skip the grace window — set old secret to invalid
   immediately. For JWT specifically, see
   [`disaster-recovery.md`](./disaster-recovery.md) §3.4 (HS256 grace
   collapse).
5. **Investigate while monitoring.** What did the attacker do with the
   secret in the window before rotation? Pull access logs, query patterns,
   API call volumes.
6. **Revoke old secret in upstream system** (Anthropic console, GitHub,
   Apple, etc.) — not just AWS Secrets Manager. The secret is the secret;
   AWS is just where we store it.
7. **Force user re-auth** if user-facing tokens may have been forged
   (JWT compromise → all sessions invalid; APNs compromise → no impact
   to user sessions but rotate device-specific tokens server-side).
8. **Post-mortem within 5 business days** — template in
   [`disaster-recovery.md`](./disaster-recovery.md) §7.

### 4.3 Communication

| Audience | Channel | When |
|---|---|---|
| On-call + SRE lead | PagerDuty + Slack `#rafraf-incidents` | T+0 |
| Engineering | Slack `#rafraf-engineering` | T+15 |
| Customers (if user-facing tokens compromised, e.g., JWT) | Push notification + email + statuspage banner | T+30 |
| Regulators (if PII may have been accessed) | Per legal counsel (GDPR — 72h notification window) | Per counsel |

---

## 5. Drill schedule

To make sure procedures actually work when needed:

| Cadence | Drill | Environment | Owner | Pass criteria |
|---|---|---|---|---|
| **Quarterly** | Full rotation drill against staging — execute §3.1 through §3.8 in sequence | `rafraf-staging` cluster | On-call rotation lead | All 8 secrets rotated, `/ready` 200 throughout, no user-facing 5xx, total elapsed time recorded |
| **Quarterly** | Compromise drill — pick one secret at random, simulate leak, run §4.2 | Staging | SRE lead | Time-to-revoke < 5 min, post-drill writeup in `docs/runbooks/drills/` |
| **Annually** | Tabletop exercise — walk through hostile-departure scenario (no actual rotation) | N/A (paper exercise) | SRE lead + engineering manager | Coverage of all secrets the persona had access to, no gaps in matrix §1 |

Drill results are appended to
[`docs/runbooks/disaster-recovery-drill-log.md`](./disaster-recovery-drill-log.md)
under a new section "Secret rotation drills".

---

## 6. Owner & Last Reviewed

- **Owner:** SRE lead (TBD per org). Per-secret owners listed in §1.
- **Last reviewed:** 2026-05-02 (initial creation, T3.8 / Faz 3)
- **Next review due:** 2026-08-02 (90 days; quarterly cadence)
- **Change log:**

| Date | Author | Change |
|---|---|---|
| 2026-05-02 | T3.8 agent | Initial runbook — 12-row inventory, general rotation procedure with grace-window guidance, per-secret CLI commands (JWT/DB/Redis/Anthropic/APNs/IRSA-note/GHCR/bridge), emergency compromise path with decision matrix, drill schedule |

---

**End of runbook.** For routine rotation, jump to §3.x for the specific
secret. For compromise response, jump to §4.
</content>
</invoke>