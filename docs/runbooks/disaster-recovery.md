# Disaster Recovery Runbook — RafRaf

> Operational procedures for recovering RafRaf (backend + bridge + persistence)
> from data loss, region outage, secrets compromise, and accidental destructive
> operations. Source of truth for on-call incident response.

**Cross-references:**
- [`docs/10_Production_Pivot_Spec.md`](../10_Production_Pivot_Spec.md) §7.5 — RPO/RTO targets
- [`docs/runbooks/jwt-key-rotation.md`](./jwt-key-rotation.md) — JWT key rotation procedure (T2.9)
- [`infra/scripts/backup-dev-db.sh`](../../infra/scripts/backup-dev-db.sh) — manual backup helper

---

## 1. Scope & Objectives

### Targets

| Metric | Target | Notes |
|---|---|---|
| **RPO** (Recovery Point Objective) | **24 hours** | Max acceptable data loss; daily snapshots + PITR cover this |
| **RTO** (Recovery Time Objective) | **1 hour** | Max time from incident declaration to `/ready` returning 200 in production |
| **Drill frequency** | Monthly (restore), quarterly (chaos), annual (full DR) | See §5 |

### In-scope disaster scenarios

| # | Scenario | Detection | Primary procedure |
|---|---|---|---|
| 1 | **Postgres data loss / corruption** | `/ready` 503, alembic mismatch, query errors | §3.1 (RDS snapshot) or §3.3 (pg_dump) |
| 2 | **Accidental `DROP DATABASE` / `TRUNCATE`** | Audit log, user reports | §3.2 (PITR to seconds before incident) |
| 3 | **Region / AZ outage** | AWS Health Dashboard, multi-AZ health check failures | Failover to cross-region replica (V2) or restore to alternate region |
| 4 | **Secrets compromise (JWT private key, ANTHROPIC_API_KEY, APNs)** | GitHub secret-scan alert, abnormal auth pattern, key in public source | §3.4 (immediate rotation + invalidate tokens) |
| 5 | **Ransomware / encrypted volumes** | Read failures on EBS / Mac disk, ransom note | Restore from offsite S3 backup; never pay |
| 6 | **Hardware failure (Mac local prod, VPS host down)** | SSH unreachable, smartctl errors | Re-provision host, restore from latest S3 backup |
| 7 | **Redis loss** | `/ready` 503 for Redis check | §3.5 (cold restart; users re-login) |
| 8 | **Bridge daemon stuck / unrecoverable** | iOS sees `bridge.unavailable`, repeated heartbeat misses | Restart `rafraf-bridge` LaunchAgent on host Mac; not a DR scenario per se but document handoff |

### Out of scope

- **Anthropic Claude API outage** — handled by `bridge.unavailable` path; iOS surfaces a maintenance banner. No restore procedure; wait for Anthropic status page.
- **iOS App Store outage** — users keep current installed binary; no server-side action.
- **DNS provider outage** — fall back to direct IP if needed; not covered here.
- **Source code loss** — git is distributed; recover from any clone (developers, GitHub, CI cache). No backup procedure beyond standard branch protection.

---

## 2. Backup Strategy

### 2.1 Postgres

#### Production (RDS — Faz 3 EKS deploy target)

- **Automated snapshots**: daily, 7-day retention, encrypted with KMS.
- **PITR (Point-in-Time Recovery)**: enabled for last 7 days (5-minute granularity, transaction logs in S3).
- **Cross-region snapshot replica**: `eu-central-1` primary → `eu-west-1` replica daily; KMS re-encrypted with target-region CMK.
- **Manual snapshot before risky migrations**: ops creates `pre-<migration>-<date>` snapshot from console; retained 90 days.

```bash
# Manual snapshot before risky migration
aws rds create-db-snapshot \
  --db-instance-identifier rafraf-prod \
  --db-snapshot-identifier "pre-$(date +%Y%m%d-%H%M%S)-manual"
```

#### Self-hosted (VPS / Mac local — Faz 2 default)

- **Daily cron** at 02:00 local time:

  ```cron
  0 2 * * * /opt/rafraf/scripts/backup-postgres-prod.sh
  ```

- Script writes `pg_dump --format=custom` to `$BACKUP_DIR/<timestamp>.dump`, then uploads to `s3://${AWS_S3_BUCKET}/postgres-backups/<YYYY/MM/DD>/<host>-<timestamp>.dump` with versioning enabled and SSE-S3 encryption.
- **Bucket policy**: deny `s3:DeleteObject*` to all principals except a dedicated lifecycle role; protects against ransomware deleting backups.

#### Local dev

- [`infra/scripts/backup-dev-db.sh`](../../infra/scripts/backup-dev-db.sh) — manual + run automatically before destructive ops (T0.1 / T0.12 / T2.5 — pre-migration backups).
- Output: `~/Code/rafraf-backups/<timestamp>.sql.gz`.
- Not part of the DR baseline; never used to restore production.

#### Retention

| Tier | Storage | Retention | Cost |
|---|---|---|---|
| Hot | S3 Standard (`postgres-backups/`) | 30 days | ~$0.023/GB/mo |
| Cold | S3 Glacier Deep Archive (`postgres-backups-archive/`) | 365 days | ~$0.00099/GB/mo |
| RDS automated snapshots | RDS storage | 7 days | included with RDS |

S3 lifecycle policy snippet:

```json
{
  "Rules": [
    {
      "ID": "rafraf-postgres-backups-tiering",
      "Status": "Enabled",
      "Filter": { "Prefix": "postgres-backups/" },
      "Transitions": [
        { "Days": 30, "StorageClass": "DEEP_ARCHIVE" }
      ],
      "Expiration": { "Days": 365 }
    }
  ]
}
```

### 2.2 Redis

- **Production (ElastiCache)**: daily automatic snapshot, 7-day retention; restore via `aws elasticache create-cache-cluster --snapshot-name`.
- **Self-hosted Redis**: enable AOF persistence (`appendonly yes`) + daily RDB snapshot copied to S3.
- **Local dev**: cache-only (rebuildable); no backup needed.
- **Note for ops**: refresh-token state and rate-limit counters live in Redis. Loss = all users re-login on next request; not a true disaster, but post a brief Slack note in `#rafraf-ops` so support knows why login spike happened.

### 2.3 Application secrets

| Secret | Storage | Backup mechanism |
|---|---|---|
| JWT keys (RS256 keypair, T2.9) | K8s `Secret` synced from AWS Secrets Manager via External Secrets Operator (ESO) | Secrets Manager versioning + cross-region replica |
| `ANTHROPIC_API_KEY` (V1.1+ fallback only) | Same as JWT | Same |
| `DATABASE_URL`, `REDIS_URL` | K8s `Secret` from Secrets Manager | Same |
| Apple APNs `.p8` key | K8s `Secret` (base64) | Encrypted S3 bucket `s3://${AWS_S3_BUCKET}/secrets/apns/` (KMS, restricted IAM) |
| `GITHUB_TOKEN` (CI) | GitHub Actions secret + 1Password | 1Password vault (manual record) |
| Bridge `BRIDGE_AUTH_TOKEN` | K8s `Secret` | Secrets Manager |

**Never** commit secrets to git. GitHub secret-scanning + push protection are enabled on the repo.

### 2.4 Source code & infrastructure

- **GitHub repo** is distributed by definition; every developer clone + GitHub origin + CI artifact cache provide redundancy. No additional backup.
- **Helm charts / Terraform**: live in `infra/` inside the repo, versioned with semver tags + protected `main` branch.
- **Container images**: pushed to `ghcr.io/atknatk/rafraf-backend` and `ghcr.io/atknatk/rafraf-bridge` with 90-day retention. Optionally synced nightly to ECR (`<account>.dkr.ecr.eu-central-1.amazonaws.com/rafraf-backend`) for AWS-internal pulls and disaster failover when GHCR is unreachable.

---

## 3. Restore Procedures

> All commands assume the operator has assumed the `rafraf-sre` IAM role with appropriate RDS / S3 / EKS permissions, and that `kubectl` context is set to the target cluster.

### 3.1 Postgres full restore from snapshot (RDS)

**Use when:** complete data loss, instance failure, or starting from a known-good snapshot. Target total time: ≤ 60 minutes.

| Step | Command / action | Est. time |
|---|---|---|
| 1. Declare incident | Open PagerDuty incident, post in `#rafraf-incidents` | 2 min |
| 2. Stop writers | `kubectl scale deploy/rafraf-backend -n rafraf --replicas=0` | 1 min |
| 3. Identify snapshot | `aws rds describe-db-snapshots --db-instance-identifier rafraf-prod --snapshot-type automated --query 'DBSnapshots[?Status==\`available\`] \| sort_by(@, &SnapshotCreateTime) \| [-1].DBSnapshotIdentifier'` | 2 min |
| 4. Restore snapshot to new instance | `aws rds restore-db-instance-from-db-snapshot --db-instance-identifier rafraf-prod-restore --db-snapshot-identifier <snapshot-id> --db-instance-class db.t4g.small --vpc-security-group-ids <sg-id> --db-subnet-group-name rafraf-prod` | 15-25 min (RDS provision) |
| 5. Wait for `available` | `aws rds wait db-instance-available --db-instance-identifier rafraf-prod-restore` | included above |
| 6. Sanity check | `psql "$RESTORE_URL" -c "SELECT version_num FROM alembic_version;"` and row counts (see §8) | 2 min |
| 7. Swap connection | Update `DATABASE_URL` in `Secret` to point at restored endpoint; force ESO refresh: `kubectl annotate externalsecret rafraf-secrets force-sync=$(date +%s) -n rafraf --overwrite` | 3 min |
| 8. Resume backend | `kubectl scale deploy/rafraf-backend -n rafraf --replicas=2` | 1 min |
| 9. Verify | `curl https://backend.rafraf.app/ready` returns 200; smoke test login + send-message | 5 min |
| 10. Close incident | Update PagerDuty + statuspage; schedule post-mortem within 48h | 2 min |
| **Total** | | **~55 min** |

If step 4 takes longer than 30 min, escalate to AWS support (Premium plan) — restore is critical-path.

### 3.2 Postgres PITR (point-in-time recovery)

**Use when:** corruption happened at a known time (e.g., bad migration ran at 14:32), need to restore to a precise moment before the event.

```bash
# Identify safe restore time (1 minute before incident)
TARGET_TIME="2026-05-02T14:31:00Z"

# Restore to a new instance — DOES NOT touch the live one
aws rds restore-db-instance-to-point-in-time \
  --source-db-instance-identifier rafraf-prod \
  --target-db-instance-identifier rafraf-prod-pitr \
  --restore-time "$TARGET_TIME" \
  --db-instance-class db.t4g.small \
  --vpc-security-group-ids <sg-id> \
  --db-subnet-group-name rafraf-prod

aws rds wait db-instance-available --db-instance-identifier rafraf-prod-pitr

# Compare row counts against live before swap; if good, follow steps 7-9 from §3.1
```

PITR window is 7 days. If the incident is older than 7 days, fall back to §3.1 with the closest snapshot.

### 3.3 Postgres restore from `pg_dump` (self-hosted / dev)

**Use when:** running on VPS/Mac without RDS, or restoring local dev DB before re-running an integration test.

```bash
# 1. Stop backend (so no writers race the restore)
#    Production self-hosted (systemd):
sudo systemctl stop rafraf-backend
#    Or k8s:
kubectl scale deploy/rafraf-backend -n rafraf --replicas=0
#    Or local dev:
docker compose -f infra/docker/docker-compose.dev.yml stop backend

# 2. Drop & recreate DB (DESTRUCTIVE — confirm twice)
psql -h "$DB_HOST" -U postgres -c "DROP DATABASE IF EXISTS rafraf;"
psql -h "$DB_HOST" -U postgres -c "CREATE DATABASE rafraf OWNER rafraf;"

# 3a. Restore from gzipped plain SQL (the format produced by backup-dev-db.sh)
gunzip -c <backup>.sql.gz | psql -h "$DB_HOST" -U rafraf -d rafraf

# 3b. OR restore from custom-format dump (production self-hosted default)
pg_restore -h "$DB_HOST" -U rafraf -d rafraf -j 4 -v <backup>.dump

# 4. Verify schema head matches expected migration
psql -h "$DB_HOST" -U rafraf -d rafraf -c "SELECT version_num FROM alembic_version;"
# Expected: same head as `cd apps/backend && alembic heads` on the deployed branch.

# 5. Sanity row counts
psql -h "$DB_HOST" -U rafraf -d rafraf -c "
  SELECT 'users' AS tbl, count(*) FROM users
  UNION ALL SELECT 'sessions', count(*) FROM sessions
  UNION ALL SELECT 'messages', count(*) FROM messages
  UNION ALL SELECT 'agents', count(*) FROM agents;"

# 6. Restart backend
sudo systemctl start rafraf-backend   # OR kubectl scale ... --replicas=2

# 7. Verify /ready
curl https://backend.rafraf.app/ready   # expect 200 with {"db":"ok","redis":"ok"}
```

### 3.4 JWT key rotation post-compromise

**Use when:** the JWT signing private key is leaked (GitHub push, screen-share, dump in error log, departing employee).

See [`docs/runbooks/jwt-key-rotation.md`](./jwt-key-rotation.md) (T2.9) for the full standard rotation procedure. **DR-specific differences:**

1. Treat as a P0 — page on-call, post in `#rafraf-incidents` immediately. Time matters: every minute is forged-token risk.
2. **Rotate immediately** — do not wait for the scheduled rotation window. Generate a new RSA-4096 keypair locally:
   ```bash
   openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:4096 -out jwt-private.pem
   openssl rsa -in jwt-private.pem -pubout -out jwt-public.pem
   ```
3. Push new keys into AWS Secrets Manager:
   ```bash
   aws secretsmanager update-secret --secret-id rafraf/jwt-keys --secret-string "$(jq -n --arg priv "$(cat jwt-private.pem)" --arg pub "$(cat jwt-public.pem)" '{private:$priv,public:$pub}')"
   ```
4. **Invalidate all existing access tokens** by setting `JWT_LEGACY_GRACE_UNTIL=0` in the same secret (normal rotation gives a grace window; compromise must not). Force ESO sync:
   ```bash
   kubectl annotate externalsecret rafraf-secrets force-sync=$(date +%s) -n rafraf --overwrite
   kubectl rollout restart deploy/rafraf-backend -n rafraf
   ```
5. All users will be force-logged out. iOS clients receive `401`, refresh-token flow also fails (refresh tokens are signed with the same key), so iOS falls back to Apple Sign In re-auth. Communicate via push notification + statuspage banner (template in §6).
6. **Securely shred the leaked key material**. If leaked via git, follow GitHub's [removing sensitive data](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository) procedure (BFG Repo-Cleaner) and rotate any other secrets that were near it.
7. Open a post-mortem within 24h (template in §7) — rotation is response, not closure.

### 3.5 Redis flush + cold rebuild

**Use when:** Redis data is corrupted or unrecoverable; rate-limit counters and refresh-token state are lost. NOT a DR-level event but document the procedure.

```bash
# Production (ElastiCache): create new cluster from snapshot OR
aws elasticache delete-cache-cluster --cache-cluster-id rafraf-redis-prod
# (then re-provision from Terraform / Helm)

# Self-hosted: flush and restart
redis-cli -h "$REDIS_HOST" -a "$REDIS_PASSWORD" FLUSHDB
sudo systemctl restart redis

# Verify backend health
curl https://backend.rafraf.app/ready
# Expect 200; first request after flush populates rate-limit buckets fresh.
```

**Side-effect:** all logged-in users must re-authenticate on next API call. Notify support and post in `#rafraf-ops` ("Redis cold restart at 14:22 UTC; brief login spike expected").

---

## 4. Monitoring & Detection

All metrics defined in T2.2 (Prometheus). Alerting rules live in `infra/k8s/monitoring/alert-rules.yaml`.

| Trigger | Threshold | Channel | Owner |
|---|---|---|---|
| Postgres unreachable | `pg_up == 0` for > 1 min | PagerDuty (P1) | on-call |
| `/ready` returns 503 | > 5 min sustained | PagerDuty (P1) + Slack `#rafraf-incidents` | on-call |
| `/ready` returns 503 | > 30 sec | Slack `#rafraf-ops` (warn) | on-call |
| Redis unreachable | `redis_up == 0` for > 2 min | Slack `#rafraf-ops` | on-call |
| Backend pod CrashLoopBackOff | Any in `rafraf` namespace | PagerDuty (P2) | on-call |
| Cost spike (Anthropic API) | `claude_total_cost_usd_total` rate > $50/h | Slack `#rafraf-ops` | finance + on-call |
| Subscription overage warning | `claude_5h_usage_pct > 90` for > 5 min | Slack `#rafraf-ops` | on-call |
| JWT verification failure spike | `jwt_verify_errors_total` rate > 50/min | Slack `#rafraf-incidents` (possible compromise) | on-call + security |
| Bridge unavailable | `bridge_connected{instance=...} == 0` for > 2 min | Slack `#rafraf-ops` | on-call (notify bridge owner) |
| Backup job failed | `postgres_backup_last_success_seconds > 86400` (no success in 24h) | PagerDuty (P2) | on-call |

**Detection latency target**: < 2 min from incident to first page; achieved by 1-min Prometheus scrape + 30-sec evaluation interval.

---

## 5. Drill Schedule

| Cadence | Drill | Environment | Owner | Documentation |
|---|---|---|---|---|
| **Monthly** | Restore from latest snapshot, time end-to-end (steps 1-9 in §3.1) | Staging (`rafraf-staging` cluster) | On-call rotation lead | Append result to `docs/runbooks/disaster-recovery-drill-log.md` (created on first drill) |
| **Quarterly** | Chaos drill — kill primary AZ via AWS Fault Injection Simulator; verify multi-AZ failover (V2 only) | Staging | SRE lead | Same log |
| **Annually** | Full DR exercise — wipe staging, restore from S3 backup, run full e2e smoke suite, verify all integrations | Staging | SRE lead + engineering manager | Same log + executive summary |

**Pass criteria (monthly):** RTO actual ≤ 1h, no data integrity errors, `/ready` returns 200 within RTO. **Deviation > 25%** from RTO target → reassess procedure within 1 week, update this runbook.

**Owner of this runbook**: SRE lead (TBD per org); on-call rotation runs the drills.

---

## 6. Communication Plan

### Channels

| Channel | Purpose | Audience |
|---|---|---|
| `#rafraf-incidents` (Slack) | Live incident updates, paging | On-call, eng leads, exec |
| `#rafraf-ops` (Slack) | Action coordination, warn-level alerts | On-call, SRE, support |
| `#rafraf-engineering` (Slack) | FYI broadcasts, post-mortem links | All engineering |
| PagerDuty `rafraf-prod` service | P1/P2 paging | On-call rotation |
| Statuspage (`status.rafraf.app`) | Customer-facing status | All users |

### Statuspage update template

```text
[Investigating] We are investigating reports of degraded service affecting <login / chat / project sync>.
We will post the next update in 15 minutes.
[Posted: <UTC time>]

[Identified] We have identified the cause as <brief, jargon-free>.
A fix is being applied; ETA <estimate>.
[Posted: <UTC time>]

[Monitoring] A fix has been applied. We are monitoring service for full recovery.
[Posted: <UTC time>]

[Resolved] Service has been fully restored. A post-mortem will be published within 5 business days at <link>.
[Posted: <UTC time>]
```

### Customer comms

| Severity | Channel | Trigger |
|---|---|---|
| Backend down ≤ 15 min | Statuspage only | — |
| Backend down 15-30 min | Statuspage + Slack to TestFlight beta channel | T+15 |
| Backend down > 30 min | + Push notification to all users + email to TestFlight beta | T+30 |
| Data loss confirmed (any duration) | + In-app banner + email to all users + statuspage incident with severity "major" | Immediate |
| Secrets compromise affecting users | + Force re-login + push notification + email + statuspage | Immediate |

Push notification payload uses APNs silent push to invalidate session, then a visible push: "RafRaf is undergoing maintenance. Please re-open the app shortly."

---

## 7. Post-Incident Review

Filed within **5 business days** at `docs/postmortems/<YYYY-MM-DD>-<slug>.md`. Use this template:

```markdown
# Post-Incident Review: <slug>

**Incident date:** YYYY-MM-DD HH:MM UTC
**Detected:** YYYY-MM-DD HH:MM UTC (T+? from root cause)
**Resolved:** YYYY-MM-DD HH:MM UTC (T+? from detection)
**Severity:** P1 / P2 / P3
**Author:** <name>
**Reviewers:** <names>

## Summary
2-3 sentence layperson-readable description.

## Impact
- Users affected: <count or %>
- Data loss: <none / count of records / time window>
- Revenue / cost impact: $<estimate>
- Downstream impact: <iOS app, partner integrations, etc.>

## Timeline
| Time (UTC) | Event |
|---|---|
| 14:30 | <event> |
| 14:32 | Alert fired |
| 14:35 | On-call acknowledged |
| ... | ... |
| 15:25 | Service restored |

## Root cause (5 whys)
1. Why did the outage happen? <answer>
2. Why was that possible? <answer>
3. Why was that not caught? <answer>
4. Why was the gap not addressed earlier? <answer>
5. Why is the system designed this way? <answer>

## What went well
- <bullet>

## What went poorly
- <bullet>

## Action items
| # | Action | Owner | Due | Tracking |
|---|---|---|---|---|
| 1 | <action> | @<owner> | YYYY-MM-DD | #<issue> |
| 2 | ... | ... | ... | ... |

## Follow-up backlog
- Items that didn't make the action list but are worth tracking long-term.
```

The author is the on-call who closed the incident; reviewers include SRE lead + at least one engineer who participated. Action items must have owners and due dates — no anonymous "TODO".

---

## 8. Useful Commands Reference

### `pg_dump` variants

```bash
# Plain SQL gzipped (legacy, what backup-dev-db.sh produces)
pg_dump -h "$DB_HOST" -U rafraf rafraf | gzip > backup.sql.gz

# Custom format (faster restore, parallel, recommended for production self-hosted)
pg_dump -h "$DB_HOST" -U rafraf --format=custom --file=backup.dump rafraf

# Schema-only (for migration sanity checks)
pg_dump -h "$DB_HOST" -U rafraf --schema-only rafraf > schema.sql

# Single table (e.g., users table for forensic copy)
pg_dump -h "$DB_HOST" -U rafraf --table=users --data-only rafraf > users.sql
```

### `psql` common queries during incident

```sql
-- Confirm migration head matches deployed branch
SELECT version_num FROM alembic_version;

-- Row counts for sanity
SELECT 'users' AS tbl, count(*) FROM users
UNION ALL SELECT 'sessions', count(*) FROM sessions
UNION ALL SELECT 'messages', count(*) FROM messages
UNION ALL SELECT 'agents', count(*) FROM agents
UNION ALL SELECT 'projects', count(*) FROM projects;

-- Active connections (are writers stuck?)
SELECT pid, usename, application_name, state, query_start, query
FROM pg_stat_activity
WHERE state != 'idle'
ORDER BY query_start;

-- Long-running queries (> 5 min)
SELECT pid, now() - query_start AS duration, query
FROM pg_stat_activity
WHERE state != 'idle' AND now() - query_start > interval '5 min';

-- Kill a stuck query (use with extreme care)
SELECT pg_terminate_backend(<pid>);

-- Replication lag (RDS read replica)
SELECT now() - pg_last_xact_replay_timestamp() AS replication_lag;

-- Disk usage by table
SELECT schemaname, relname, pg_size_pretty(pg_total_relation_size(relid)) AS size
FROM pg_catalog.pg_statio_user_tables
ORDER BY pg_total_relation_size(relid) DESC LIMIT 20;
```

### `kubectl` rollback / scale

```bash
# Stop traffic to backend (writers off)
kubectl scale deploy/rafraf-backend -n rafraf --replicas=0

# Resume
kubectl scale deploy/rafraf-backend -n rafraf --replicas=2

# Rollback to previous deployment
kubectl rollout undo deploy/rafraf-backend -n rafraf

# Check rollout history
kubectl rollout history deploy/rafraf-backend -n rafraf

# Force restart (e.g., after secret change)
kubectl rollout restart deploy/rafraf-backend -n rafraf

# Tail logs across all backend pods
kubectl logs -n rafraf -l app=rafraf-backend --tail=100 -f --max-log-requests=10
```

### Redis (use with care)

```bash
# Inspect memory + connected clients
redis-cli -h "$REDIS_HOST" INFO memory
redis-cli -h "$REDIS_HOST" CLIENT LIST

# Count refresh tokens (sanity check post-restart)
redis-cli -h "$REDIS_HOST" --scan --pattern 'refresh:*' | wc -l

# Flush selected DB (DESTRUCTIVE — confirm first)
redis-cli -h "$REDIS_HOST" -n 0 FLUSHDB
```

### Alembic

```bash
cd apps/backend

# Show current head
alembic current

# Show all heads (multi-head detection)
alembic heads

# Upgrade to latest
alembic upgrade head

# Downgrade one revision (DANGEROUS in production)
alembic downgrade -1

# Generate SQL without executing (review before applying)
alembic upgrade head --sql > /tmp/migration.sql
```

### Backup verification (one-liner)

```bash
# Verify the most recent S3 backup is < 24h old (RPO check)
LATEST=$(aws s3 ls "s3://${AWS_S3_BUCKET}/postgres-backups/" --recursive | sort | tail -1)
echo "$LATEST"
# Manual eyeball: timestamp should be within last 24h.
```

---

## 9. Owner & Last Reviewed

- **Owner:** SRE lead (TBD per org — assign when team is staffed)
- **Last reviewed:** 2026-05-02 (initial creation, T2.8 / Faz 2)
- **Next review due:** 2026-08-02 (90 days; quarterly cadence)
- **Change log:** record material updates here.

| Date | Author | Change |
|---|---|---|
| 2026-05-02 | T2.8 agent | Initial runbook — RPO/RTO, backup strategy, restore procedures, drills, comms, post-incident template, command reference |

---

**End of runbook.** For incident-time use, jump to §3 (Restore Procedures) and §8 (Useful Commands). For drill planning, see §5. For comms, §6.
