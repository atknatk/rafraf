# Grafana Dashboards — Catalogue

> RafRaf does not yet ship Grafana dashboards as code. This file is the
> **metric catalogue** SREs should reference when authoring dashboards
> against the production Prometheus scrape target. Faz 4 will land the
> first JSON-defined dashboards under `infra/grafana/dashboards/`.

| Field         | Value                                  |
|---------------|----------------------------------------|
| Owner         | Backend / SRE                          |
| Last Reviewed | 2026-05-02 (V1.6 — permission counters)|
| Source        | `apps/backend/app/core/metrics.py`     |

---

## V1.4 — Permission flow counters

The bridge → backend → iOS permission round-trip emits three Prometheus
counters from the backend handler. Together they partition the lifecycle
so a single dashboard panel can plot emit / decide / timeout on the same
chart and answer the SRE question "what fraction of permission_requests
are auto-denying?" without joining counters cross-component.

Defined in `apps/backend/app/core/metrics.py` (lines 124–148, V1.4).

### `permission_request_emitted_total`

| Attribute   | Value                                                     |
|-------------|-----------------------------------------------------------|
| Type        | Counter                                                   |
| Labels      | `bridge_id`, `tool_name`, `risk`                          |
| Incremented | On backend receipt of `event.session.permission_request`  |
| Description | `permission_request envelopes received from bridges.`     |

**Suggested panels:**
- **Stat** — Total permission requests in window (rate, 5m).
- **Time series** — `sum by (risk) (rate(permission_request_emitted_total[5m]))`
  to spot risk-band shifts (e.g. unexpected `high` spike =
  off-whitelist Bash storm).
- **Table** — top 10 `tool_name` values by count, partitioned by
  `bridge_id`.

### `permission_request_decided_total`

| Attribute   | Value                                                       |
|-------------|-------------------------------------------------------------|
| Type        | Counter                                                     |
| Labels      | `bridge_id`, `tool_name`, `decision`                        |
| Incremented | When `_await_and_dispatch_decision` resolves and dispatches |
| Description | `permission_request decisions dispatched back to bridges.`  |

`decision` label values: `approved`, `rejected`, `expired`,
`dispatch_failed`.

**Suggested panels:**
- **Pie chart** — decision distribution (approved vs. rejected vs.
  expired vs. dispatch_failed).
- **Time series** — `sum by (decision) (rate(permission_request_decided_total[5m]))`.
- **Stat — auto-deny rate** —
  `sum(rate(permission_request_decided_total{decision="expired"}[5m])) /
  sum(rate(permission_request_decided_total[5m]))`. Alert at > 0.20.

### `permission_request_timeout_total`

| Attribute   | Value                                                  |
|-------------|--------------------------------------------------------|
| Type        | Counter                                                |
| Labels      | `bridge_id`, `tool_name`                               |
| Incremented | On RFApprovalSheet auto-timeout / awaiter timeout      |
| Description | `permission_request decisions that hit the timeout (auto-deny).` |

**Suggested panels:**
- **Stat** — Timeouts in window (rate, 5m).
- **Time series** — per-tool to spot UX issues (high timeout rate on
  one tool = the question text or risk classification needs review).

---

## Cross-references

- Metric definitions: `apps/backend/app/core/metrics.py:124-148`.
- Emit sites: `apps/backend/app/api/routes/websocket.py`
  (`_await_and_dispatch_decision`,
  `_handle_permission_request_event`) — V1.4 commit 8a43991 +
  V1.4-fix HIGH commit 811ea0f.
- Latency budgets these counters live within: see
  `docs/runbooks/permission-flow.md` §13.
- End-to-end design context:
  `docs/design/v1-permission-blockers.md` §5.2.
- Wire envelopes that drive these counters:
  `shared/api-contracts/ws/bridge-permission-messages.json`.

When Faz 4 ships JSON-defined dashboards, this README converts to a
dashboard provisioning manifest and the panels above become the
canonical "Permission Flow" board.
