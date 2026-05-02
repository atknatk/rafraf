# RafRaf Runbooks

Operational runbooks for incident response, routine procedures, and disaster recovery.
Each runbook should be self-contained, dated, and reviewed quarterly.

## Index

### Deploy

| Runbook | Purpose | Owner | Last reviewed |
|---|---|---|---|
| [`deploy.md`](./deploy.md) | Production deploy procedure — backend EKS via Helm/ArgoCD + bridge `.pkg` distribution + iOS TestFlight promote (T3.8 / Faz 3) | SRE lead | 2026-05-02 |

### Security

| Runbook | Purpose | Owner | Last reviewed |
|---|---|---|---|
| [`jwt-key-rotation.md`](./jwt-key-rotation.md) | JWT signing keypair rotation procedure (RS256, T2.9 / Faz 2) — covers HS256 → RS256 cutover and routine RS256 rotation | SRE lead | 2026-05-02 |
| [`secret-rotation.md`](./secret-rotation.md) | Routine + emergency rotation procedures for all production secrets (JWT, DB, Redis, Anthropic, APNs, GitHub PAT, bridge pairing token, GHCR pull, AWS keys) (T3.8 / Faz 3) | SRE lead | 2026-05-02 |
| [`disaster-recovery.md`](./disaster-recovery.md) | RPO/RTO targets, backup strategy, restore procedures, drill schedule, comms plan, post-incident template (T2.8 / Faz 2) | SRE lead | 2026-05-02 |
| [`disaster-recovery-drill-log.md`](./disaster-recovery-drill-log.md) | Chronological per-drill log + template (companion to `disaster-recovery.md` §5; T2.8-fix / Faz 2) | SRE lead | 2026-05-02 |
| [`permission-flow.md`](./permission-flow.md) | claude tool permission flow (Spike #5 fallback tree, V1 acceptEdits + Bash whitelist, approval flow E2E, audit log) (T3.2 / Faz 3) | Backend lead | 2026-05-02 |

### Maintenance

| Runbook | Purpose | Owner | Last reviewed |
|---|---|---|---|
| [`anthropic-cli-upgrade.md`](./anthropic-cli-upgrade.md) | claude CLI upgrade procedure for Mac bridge hosts — weekly check, stream-json schema drift detection, rollback (T3.8 / Faz 3) | Bridge owner | 2026-05-02 |

### Test

| Runbook | Purpose | Owner | Last reviewed |
|---|---|---|---|
| [`manual-test-checklist.md`](./manual-test-checklist.md) | Pre/post-TestFlight manual test checklist for iOS builds — functional grid, performance, network conditions, accessibility, 3h soak, sign-off (T3.4 / T3.8 / Faz 3) | iOS lead + QA | 2026-05-02 |

## Conventions

- **File naming:** `kebab-case.md` describing the procedure (verb-noun preferred: `rotate-jwt`, `restore-database`).
- **Required sections:** scope, prerequisites, step-by-step procedure with commands, verification steps, rollback, owner, last-reviewed date.
- **Cross-link:** runbooks should link to relevant spec sections in `docs/10_Production_Pivot_Spec.md`, action items in `docs/12_Action_Plan_Tasks.md`, and any sibling runbook they depend on.
- **No secrets in runbooks.** Reference secret names and storage locations; never paste actual values.
- **Review cadence:** quarterly (every 90 days). Update the "Last reviewed" date and append to the change-log table at the bottom of each runbook.

## Related directories

- [`../postmortems/`](../postmortems/) — incident post-mortems filed within 5 business days of resolution (template in `disaster-recovery.md` §7).
- [`../standards/`](../standards/) — platform-specific coding standards.
- [`../pipeline/`](../pipeline/) — agent pipeline handoff docs.
- [`./drills/`](./drills/) — recorded DR drill execution reports (referenced by `disaster-recovery-drill-log.md`).
