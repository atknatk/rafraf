# Production Deploy Runbook (T3.8)

> Standard procedure for promoting a green build of the RafRaf system into
> production. Covers three deploy artifacts that ship together but on
> independent cadences:
>
> 1. **Backend** (FastAPI) — EKS cluster, deployed via Helm chart synced by
>    ArgoCD; image pulled from `ghcr.io/atknatk/rafraf-backend`.
> 2. **Bridge** (Go daemon) — Mac user host, distributed as a signed
>    `.pkg` (Apple Developer ID) per T3.6.
> 3. **iOS** — promoted from internal TestFlight to external testers,
>    then phased rollout to App Store.
>
> **Cross-references:**
> - [`docs/10_Production_Pivot_Spec.md`](../10_Production_Pivot_Spec.md) §8 (Faz 3 plan), §9.1 (deploy options)
> - [`docs/12_Action_Plan_Tasks.md`](../12_Action_Plan_Tasks.md) §6 T3.5/T3.6/T3.7/T3.8
> - [`docs/runbooks/secret-rotation.md`](./secret-rotation.md) — bridge `pairing_token` migration during deploy
> - [`docs/runbooks/jwt-key-rotation.md`](./jwt-key-rotation.md) — JWT cutover coordination
> - [`docs/runbooks/disaster-recovery.md`](./disaster-recovery.md) §3 — rollback in worst case (DB-level restore)
> - [`docs/runbooks/manual-test-checklist.md`](./manual-test-checklist.md) — pre-promote QA gate
> - [`apps/backend/Dockerfile`](../../apps/backend/Dockerfile) — image build
> - [`.github/workflows/backend-ci.yml`](../../.github/workflows/backend-ci.yml) — image build → GHCR push pipeline
> - [`apps/rafraf-bridge/Makefile`](../../apps/rafraf-bridge/Makefile) `pkg` target — signed installer

---

## 1. Pre-deploy checklist

Run **all** of the following before initiating any deploy. Stop and triage if
any item fails.

| # | Check | Command / source | Pass criteria |
|---|---|---|---|
| 1 | Green CI on the merge commit | `gh run list --branch develop --limit 5` | Most recent `backend-ci.yml` + `bridge-ci.yml` runs are green |
| 2 | Image exists in GHCR with the commit SHA tag | `docker manifest inspect ghcr.io/atknatk/rafraf-backend:sha-<short>` | Manifest returns 200 (not 404) |
| 3 | Alembic migration chain has a single head | `cd apps/backend && alembic heads` | Returns exactly one revision |
| 4 | Alembic head matches the production DB | Compare `alembic heads` to `psql "$DATABASE_URL_RO" -c "SELECT version_num FROM alembic_version;"` | Same revision OR new revision is a clean forward step (n+1) |
| 5 | Helm chart lints clean | `helm lint infra/k8s/helm/rafraf-backend` | Exit 0, no warnings |
| 6 | Helm template diff is reviewed | `helm diff upgrade rafraf-backend infra/k8s/helm/rafraf-backend -f infra/k8s/helm/values-prod.yaml -n rafraf` | Reviewer signs off in PR/Slack |
| 7 | Monitoring dashboards open | Grafana dashboards "RafRaf Backend (prod)" + "RafRaf Bridge fleet" | Both loaded in browser tabs by deployer |
| 8 | On-call notified | Slack `#rafraf-ops` post: "deploying backend `<sha>` in 5 min, ack to pause" | One ack from current on-call rotation |
| 9 | No active incident | PagerDuty `rafraf-prod` service | No open P1/P2 |
| 10 | Manual test checklist passed (iOS) | [`manual-test-checklist.md`](./manual-test-checklist.md) | Last sign-off ≤ 7 days old |
| 11 | Bridge `.pkg` notarization stapled | `xcrun stapler validate apps/rafraf-bridge/dist/rafraf-bridge-<version>.pkg` | "stapler 0 validate" |

> **If you are deploying outside business hours** (UTC 22:00 – 06:00) AND
> the change is non-emergency, **postpone**. Late-night deploys without a
> second pair of eyes are how rollback windows get missed.

---

## 2. Backend EKS deploy (Helm + ArgoCD)

Backend is the **first** artifact to deploy in any same-week release. Bridge
auto-detects new schema (T1.x bridge ↔ backend protocol envelope is forward
compatible); iOS submits next build only after backend is verified healthy.

### 2.1 Image tag policy

- **Always pin to commit SHA**, never `latest`. The CI workflow tags every
  push to `develop` with `sha-<short>` and pushes to `ghcr.io`. Production
  values file references the SHA explicitly:

  ```yaml
  # infra/k8s/helm/values-prod.yaml
  image:
    repository: ghcr.io/atknatk/rafraf-backend
    tag: "sha-abc1234"   # bump this; commit; ArgoCD picks up
  ```

- For semver releases (Faz 3 onward), additionally tag the SHA with
  `vMAJOR.MINOR.PATCH` (`gh release create v0.3.0 --target <sha> --title 'Faz 3 — TestFlight launch'`)
  but the Helm `image.tag` always stays SHA-pinned for traceability.

### 2.2 Sync flow (ArgoCD primary path)

| Step | Action | Verify |
|---|---|---|
| 1 | Bump `image.tag` in `infra/k8s/helm/values-prod.yaml`, open PR, merge to `main` after review | PR merged, GitOps repo updated |
| 2 | ArgoCD detects diff (auto-sync within 3 min OR click `Sync` in UI) | ArgoCD app `rafraf-backend-prod` shows `OutOfSync` → `Syncing` → `Synced` |
| 3 | Pre-install hook runs alembic Job | `kubectl logs -n rafraf job/rafraf-alembic-upgrade -f` shows `INFO  [alembic.runtime.migration] Running upgrade <prev> -> <new>` then exit 0 |
| 4 | Rolling update of Deployment | `kubectl rollout status deploy/rafraf-backend -n rafraf --timeout=10m` returns `successfully rolled out` |
| 5 | Pods become Ready | `kubectl get pods -n rafraf -l app=rafraf-backend -o wide` shows all `Running` + `READY 1/1` |
| 6 | `/ready` returns 200 from each pod | `for p in $(kubectl get pods -n rafraf -l app=rafraf-backend -o name); do kubectl exec -n rafraf $p -- curl -sf http://localhost:8000/ready && echo OK || echo FAIL; done` |
| 7 | External smoke check | `curl -sf https://backend.rafraf.app/ready -w "%{http_code}\n"` returns `200` |
| 8 | Mark ArgoCD app as healthy in dashboard | Status flips to `Healthy` automatically once readiness probes pass |

### 2.3 Manual fallback (if ArgoCD is unavailable)

```bash
# Authenticate
aws eks update-kubeconfig --name rafraf-prod --region eu-central-1
kubectl config use-context arn:aws:eks:eu-central-1:<account>:cluster/rafraf-prod

# Apply
helm upgrade rafraf-backend infra/k8s/helm/rafraf-backend \
  -f infra/k8s/helm/values-prod.yaml \
  --namespace rafraf \
  --atomic \
  --timeout 10m \
  --history-max 10

# Watch
kubectl rollout status deploy/rafraf-backend -n rafraf --timeout=10m
```

`--atomic` rolls back automatically on failure. `--history-max 10` keeps the
last 10 revisions for `helm rollback`.

---

## 3. Backend rollback

### 3.1 Application-level rollback (no migration involved)

This is the **default** rollback path — fast (< 2 min), zero data risk.

**ArgoCD path:**

1. ArgoCD UI → app `rafraf-backend-prod` → `History and Rollback` → select previous
   `Synced` revision → `Rollback`.
2. ArgoCD reconciles to the previous Helm release.
3. Verify pods Ready + `/ready` 200 (same as §2.2 steps 5-7).

**kubectl path (faster):**

```bash
# See deployment revision history
kubectl rollout history deploy/rafraf-backend -n rafraf

# Roll back one revision
kubectl rollout undo deploy/rafraf-backend -n rafraf

# Or roll back to a specific revision
kubectl rollout undo deploy/rafraf-backend -n rafraf --to-revision=<N>

# Watch
kubectl rollout status deploy/rafraf-backend -n rafraf --timeout=5m
```

**Helm path:**

```bash
helm history rafraf-backend -n rafraf
helm rollback rafraf-backend <PREV_REVISION> -n rafraf --wait --timeout 5m
```

> **Important:** `helm rollback` reverts the chart **and** the image tag to
> the previous release. If the previous release also referenced a migration
> that has since been applied, the old code may not understand the new
> schema. See §3.2.

### 3.2 Rolling back a deploy that included a migration

> **WARNING — DATA LOSS RISK.** Migrations are forward-only by default.
> Downgrading runs the `downgrade()` half of the migration which may
> **DROP COLUMNS, DROP TABLES, or DESTROY DATA** that the new version
> wrote. Read the migration file carefully **before** running
> `alembic downgrade`. If in doubt, page the schema author and the SRE lead.

Decision tree:

1. **Can the OLD code tolerate the NEW schema?** (additive migration: new
   nullable column, new table, new index — yes.)
   - **Yes** → just roll back the Deployment image (§3.1). Leave the schema
     forward; clean up dead columns later in a follow-up migration.
2. **Does the NEW schema break OLD code?** (breaking migration: dropped
   column the old code SELECTs, renamed table, NOT-NULL added without default
   that old INSERTs satisfy.)
   - **Yes** → you have two options:
     - **(Preferred)** Fix forward — push a new SHA that fixes whatever broke
       in the new code, redeploy. Keep the new schema.
     - **(Last resort)** Downgrade the schema:
       1. **Take a snapshot first** — see [`disaster-recovery.md`](./disaster-recovery.md) §2.1 (`aws rds create-db-snapshot`).
       2. Scale backend to 0 (no writers): `kubectl scale deploy/rafraf-backend -n rafraf --replicas=0`
       3. Run downgrade in a one-shot pod:
          ```bash
          kubectl run alembic-downgrade-$(date +%s) \
            --image=ghcr.io/atknatk/rafraf-backend:sha-<PREV_SHA> \
            --restart=Never \
            --rm -it \
            --env="DATABASE_URL=$(kubectl get secret rafraf-secrets -n rafraf -o jsonpath='{.data.database-url}' | base64 -d)" \
            -- alembic downgrade -1
          ```
       4. Verify: `psql ... -c "SELECT version_num FROM alembic_version;"` returns the previous head.
       5. Roll back image (§3.1).
       6. Bring backend back up: `kubectl scale deploy/rafraf-backend -n rafraf --replicas=<PRIOR>`.
       7. **Open a post-mortem** (template in `disaster-recovery.md` §7) — schema-level rollback is a P2 incident even if user-invisible.

---

## 4. Bridge `.pkg` distribution

The bridge is per-user installed software (Mac); deploy = install/upgrade on
each user's machine. Three channels in increasing rigor:

### 4.1 Dev / staging (internal team)

- Unsigned `.pkg` (or signed but not notarized) hosted on internal S3
  bucket `s3://rafraf-internal-builds/bridge/`.
- Direct download link posted in `#rafraf-ops` Slack.
- Install: `sudo installer -pkg ~/Downloads/rafraf-bridge-<version>.pkg -target /`
- Verify: `launchctl list | grep com.rafraf.bridge` returns a PID; bridge
  log shows `connected to ws://...` within 5 s.

### 4.2 Beta testers (Faz 3 launch)

- Signed `.pkg` (Apple Developer ID — team `VT3X56P4ZL` per
  `docs/12_Action_Plan_Tasks.md` T0.5.12) but distributed via private
  download (no notarization needed if Gatekeeper is not blocking).
- Hosted on `s3://rafraf-public-builds/bridge/<version>/rafraf-bridge-<version>.pkg`
  with CloudFront CDN in front; presigned URL emailed to opted-in testers.

### 4.3 Production (general availability)

- **Signed AND notarized** `.pkg`. Notarization is required so Gatekeeper
  does not block install on first launch:
  ```bash
  cd apps/rafraf-bridge
  make pkg                          # builds signed .pkg
  make notarize VERSION=<x.y.z>     # submits to Apple notary, waits for stapler
  ```
- Distributed via:
  - **Primary:** `https://download.rafraf.app/bridge/latest/rafraf-bridge.pkg`
    (CloudFront in front of S3, immutable per-version paths + `latest` symlink)
  - **Secondary:** Homebrew tap `brew install atknatk/rafraf/rafraf-bridge`
    (formula in `homebrew-rafraf` repo, auto-updated by release workflow).
- Auto-update inside the bridge daemon checks `download.rafraf.app/bridge/manifest.json`
  every 24 h and surfaces an upgrade banner via `/healthz` payload (consumed
  by iOS Settings tab).

### 4.4 Pairing token migration

If this deploy includes a change to the bridge `pairing_token` format (new
hash version, longer key, etc.), users will need to **re-pair** after
upgrade. Coordinate via:

1. Pre-deploy: post in-app banner ("Bridge update available; re-pair after install").
2. During deploy: see [`secret-rotation.md`](./secret-rotation.md) §3.7
   (bridge pairing token rotation flow).
3. Post-deploy: monitor `bridge_pair_failed_total` in Grafana; investigate
   any tester who cannot re-pair within 48 h.

> If no `pairing_token` change, this section is a no-op — existing tokens
> continue to authenticate.

---

## 5. iOS TestFlight promote

iOS deploys go **last** in any same-week release; the new app build assumes
the new backend `/ready` schema and bridge auto-update has converged.

### 5.1 Build number bump

```bash
cd apps/ios
# Bump build number (CFBundleVersion), keep marketing version (CFBundleShortVersionString)
agvtool bump -all
git add RafRaf/Info.plist RafRaf.xcodeproj/project.pbxproj
git commit -m "chore(ios): bump build number for TestFlight [release]"
```

The xcodebuild + fastlane pipeline (`.github/workflows/ios-testflight.yml`)
picks up on tag push:

```bash
git tag ios-v<x.y.z>-<build>
git push origin ios-v<x.y.z>-<build>
```

### 5.2 Internal → external testers

| Step | Action | Where |
|---|---|---|
| 1 | Build uploaded to App Store Connect | TestFlight tab → "iOS Builds" → new processing entry |
| 2 | Internal group "RafRaf Team" gets immediate access | Auto |
| 3 | Internal smoke (15 min) | At least one iOS engineer installs build, runs §5.4 sanity flow |
| 4 | Add to external group "Beta Testers" | App Store Connect → TestFlight → External Groups → Add Build |
| 5 | App Review (external only, ~24-48 h) | Apple |
| 6 | External testers receive email | TestFlight push notification |

### 5.3 Phased rollout (App Store production)

After 7-14 days of stable external TestFlight (no new crashes, manual test
checklist signed off — see [`manual-test-checklist.md`](./manual-test-checklist.md)),
submit to App Store with **phased release**:

| Day | % of users | Action |
|---|---|---|
| 1 | 10% | Submit, monitor `crash_free_users_pct` (target: ≥99.0%) |
| 2 | 10% | Hold if any new crash type appears in Sentry |
| 3 | 20% | Bump if day-2 crash-free still ≥99.0% |
| 4 | 50% | Bump |
| 5 | 50% | Hold (24h soak at 50%) |
| 6 | 100% | Bump |
| 7 | 100% | Final monitor; close release tracker |

Pause phased release at any time:
App Store Connect → "Pause Phased Release" — users on later days stay on the
previous version.

### 5.4 iOS smoke flow (15 min)

After every TestFlight build, the deployer (or designated tester) runs:

1. Sign in via Apple Sign In (fresh device or post-uninstall).
2. Open Home → see session list with AI titles (T1.8).
3. Tap a session → send message → expect streaming response within 3 s.
4. Trigger a tool that requires approval (write/bash) → approve → verify
   completion.
5. Watch for Live Activity start on Dynamic Island (T-Sprint-4).
6. Background app for 60 s → return → verify reconnect within 2 s.
7. Force-quit app → relaunch → verify session restored.

Failures here block the external promote.

---

## 6. Cross-component coordination

The three artifacts deploy on **independent cadences** but share a protocol.
Follow this order to avoid in-flight WebSocket connection breakage:

```
Backend (EKS, Helm/ArgoCD)
  ↓ (immediate; bridge reconnects within 5 s; iOS reconnects within 2 s)
Bridge (Mac users; auto-update over 24 h OR manual .pkg install)
  ↓ (rolling, no central coordination)
iOS (TestFlight; phased rollout over 7 days)
```

### 6.1 Why backend first

- Backend is the only artifact with a **central control plane** — one Helm
  upgrade rolls the fleet.
- New protocol envelope fields (e.g., new event type from T1.x Agent Teams)
  are **forward compatible** by design: bridge ignores unknown fields, iOS
  ignores unknown event types (logged at debug). So newer backend +
  older bridge/iOS works.
- The reverse — older backend + newer iOS — is **not** guaranteed. iOS
  expecting a new `event.session.title` might not find it in older backend
  output. So always: backend ahead of iOS.

### 6.2 Why NOT same-time deploy

- Same-time deploy interrupts in-flight WebSocket sessions on every
  artifact at once, multiplying user-visible reconnect blips.
- Sequential deploy lets each layer's reconnect logic absorb the
  disruption from the layer below.
- The 7-day phased iOS rollout naturally spans long enough for the bridge
  fleet to converge on the new `.pkg`.

### 6.3 Graceful drain on backend rollout

Helm rolling update + Kubernetes `preStop` hook gives existing WebSocket
sessions 30 s to drain before the pod is killed. This is configured in
`infra/k8s/helm/rafraf-backend/templates/deployment.yaml` `preStop`:

```yaml
lifecycle:
  preStop:
    exec:
      command: ["/bin/sh", "-c", "kill -SIGTERM 1; sleep 30"]
```

If you bump pod count during a deploy, do it **before** the rollout, not
during, so HPA doesn't fight the rollout.

---

## 7. Communication

### 7.1 Pre-deploy (T-15 min)

**Slack `#rafraf-ops`:**

```
:rocket: Deploying backend `<sha-short>` to prod in 15 min.
Change: <one-line summary, link to PR>
Risk: <low | med | high>
On-call: @<handle>
React :ack: to pause.
```

### 7.2 During deploy (T+0)

**Slack `#rafraf-ops` thread (reply to pre-deploy message):**

```
Started: <UTC time>
Helm rollout in progress, watching /ready.
```

### 7.3 Post-deploy (T+10 min)

**Slack `#rafraf-ops` thread:**

```
Done: <UTC time>
/ready 200, smoke pass, error rate baseline.
ArgoCD: Healthy. Grafana: nominal.
```

### 7.4 Statuspage update template

Use only for deploys with **expected user impact** (forced re-login, brief
WS reconnect storm, planned downtime):

```text
[Scheduled] We will deploy a routine update to RafRaf backend at <UTC time>.
Expected impact: <brief — e.g., "1-minute reconnect blip">.
Duration: <estimate>.
[Posted: <UTC time>]

[In progress] Deploy in progress.
[Posted: <UTC time>]

[Completed] Deploy completed successfully.
[Posted: <UTC time>]
```

For zero-impact deploys (rolling update, no schema change, no forced
re-login), no statuspage entry is required.

### 7.5 Customer comms thresholds

| Trigger | Channel |
|---|---|
| Routine deploy, no user impact | None |
| Forced re-login (e.g., JWT key rotation) | Push notification + statuspage |
| Schema migration > 5 min downtime expected | Statuspage scheduled maintenance + email to TestFlight beta channel |
| iOS new feature behind feature flag | TestFlight release notes |
| iOS breaking UX change | TestFlight release notes + in-app onboarding banner |

---

## 8. Validation post-deploy

Run **all** of the following within 10 min of rollout completion. Capture
the outputs in the deploy thread (Slack) for audit.

### 8.1 Health endpoints

```bash
curl -sf https://backend.rafraf.app/health  -w "\nHTTP %{http_code}\n"
curl -sf https://backend.rafraf.app/ready   -w "\nHTTP %{http_code}\n"
# Both must return 200. /ready body must contain {"db":"ok","redis":"ok"}.

curl -sf https://backend.rafraf.app/metrics | head -20
# Expect prometheus-format output. If 404, OTel sidecar is misconfigured.
```

### 8.2 Prometheus scrape

```bash
# From a pod inside the cluster (or via kubectl exec)
kubectl exec -n monitoring deploy/prometheus -- \
  promtool query instant http://localhost:9090 'up{job="rafraf-backend"}'
# All targets should report value=1.
```

### 8.3 Smoke test (e2e)

```bash
# Login (returns access token)
TOKEN=$(curl -sf -X POST https://backend.rafraf.app/api/v1/auth/apple \
  -H 'Content-Type: application/json' \
  -d '{"identity_token":"<test-jwt>","authorization_code":"<test-code>"}' \
  | jq -r '.access_token')

# Spawn a session (text-only smoke; no Mac bridge needed for this hop)
curl -sf -X POST https://backend.rafraf.app/api/v1/sessions \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"project_id":"<smoke-project-id>"}' | jq .id

# Cost summary endpoint (T2.5 — confirms cost tracking persists)
curl -sf https://backend.rafraf.app/api/v1/cost/summary \
  -H "Authorization: Bearer $TOKEN" | jq .
```

For a **full** e2e (claude task spawn + subagent spawn + cost record), use
the `infra/scripts/e2e-prod-smoke.sh` script (T3.7). Failure of the e2e
test is a P2 — investigate, do not auto-rollback unless errors are systemic.

### 8.4 Error rate baseline

In Grafana "RafRaf Backend (prod)" dashboard, the panel "HTTP 5xx rate
(by route)" should:

- Hold its pre-deploy median for at least 10 minutes.
- Have no individual route exceed 1% of pre-deploy traffic.

If 5xx rate doubles within 10 min of rollout → start §3.1 rollback.

### 8.5 Cost & rate-limit sanity (T2.4 / T2.5)

- `claude_total_cost_usd_total` continues to increment (not stuck at 0 — would
  indicate cost-tracker silently broke).
- `backend_rate_limit_hits_total` rate is in line with pre-deploy norm.

---

## 9. Owner & Last Reviewed

- **Owner:** SRE lead (TBD per org — assign when team is staffed). Bridge
  `.pkg` notarization owned by Mac infra (currently The Abi).
- **Last reviewed:** 2026-05-02 (initial creation, T3.8 / Faz 3)
- **Next review due:** 2026-08-02 (90 days; quarterly cadence)
- **Change log:**

| Date | Author | Change |
|---|---|---|
| 2026-05-02 | T3.8 agent | Initial runbook — pre-deploy checklist, EKS Helm/ArgoCD flow, rollback (incl. migration downgrade warning), bridge `.pkg` distribution channels, iOS TestFlight + phased rollout, cross-component coordination, comms templates, post-deploy validation |

---

**End of runbook.** For deploy-time use, run the §1 checklist, then §2 →
§4 → §5 in that order. If anything goes wrong, §3 is the first stop.
</content>
</invoke>