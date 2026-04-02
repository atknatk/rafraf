# Dark Factory Governance — RafRaf

## Governance Tiers

| Tier | Risk Score | Holdout | Satisfaction | Action |
|------|-----------|---------|-------------|--------|
| **T0: Auto-Ship** | < 15 | Pass | >= 80 | Auto-merge |
| **T1: Auto-PR** | 15-40 | Pass | >= 75 | PR + auto-approve if CI passes |
| **T2: Review-PR** | 40-60 | Pass | >= 70 | PR + 1 human review |
| **T3: Gated** | > 60 | Any | Any | PR + 2 reviews + architect |
| **T4: Blocked** | Any | Fail | < 50 | Stop, report to human |

## RafRaf-Specific Rules

- **WebSocket protocol changes**: Minimum T2 (cross-layer impact: backend + iOS + agent)
- **API contract changes**: Minimum T2 (shared/ directory is source of truth)
- **Host Agent runner changes**: Minimum T2 (security-sensitive execution)
- **Database migrations**: Minimum T1 (requires alembic review)

## Override Rules

- **Emergency Override**: Human can override any tier with explicit approval
- **Holdout Skip**: Only if no holdout scenarios exist for the affected layer
- **Night Mode**: Ralph loop only processes T0 and T1 tasks by default

## Escalation Path

1. Pipeline Doctor attempts auto-fix (max 2 retries)
2. If fix fails, task is marked as `blocked`
3. Alert is sent via configured channels
4. Human reviews and either fixes manually or cancels the task
