# Disaster Recovery Drill Log

Per-drill record of executions against `docs/runbooks/disaster-recovery.md`.
Add a new entry per drill using the template below; oldest entries pruned
after 12 months.

Logged drills (most recent first):
- 2026-05-02 — Faz 2 first restore (see docs/runbooks/drills/2026-05-02-faz2-restore-drill.md)

## Template

### YYYY-MM-DD — <drill title>
- **Owner:** <who executed>
- **Procedures executed:** <§3.1 / §3.2 / §3.3 / §3.4>
- **Pre-drill state:** alembic_version, row counts, /health, /ready
- **Measured RTO:** <X> min <Y> sec
- **Target:** ≤ 60 min
- **Status:** ✅ within budget / ⚠ exceeded
- **Deviations from runbook:** ...
- **Runbook updates needed:** ...
- **Sign-off:** <verifier>
- **Next drill due:** <date>
