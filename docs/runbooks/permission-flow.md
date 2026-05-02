# Permission Flow Runbook

> Bridge → backend → iOS approval cycle for claude tool calls. Codifies
> Spike Test #5's fallback tree (Doc 10 §2.5, §9.7) and the V1 default
> `permission_mode = acceptEdits`.

| Field          | Value                                      |
|----------------|--------------------------------------------|
| Owner          | Backend / Faz 3 squad                      |
| Last Reviewed  | 2026-05-02 (Faz 3 — T3.2 + V1.1-V1.6)      |
| Related Specs  | Doc 10 §2.5, §6.1, §9.7; Doc 11 §5; Doc 7; `docs/design/v1-permission-blockers.md` |
| Source of Truth| `apps/backend/app/services/approval_service.py`, `apps/rafraf-bridge/internal/claude/runner.go`, `apps/rafraf-bridge/internal/permission/broker.go` |

---

## 1. Scope

This runbook describes how RafRaf decides whether a tool invocation issued
by the claude CLI (running inside the Mac Go bridge) needs explicit user
approval, and how that decision flows back into the running session.

Three layers cooperate:

1. **Bridge** — `apps/rafraf-bridge/internal/claude/runner.go` launches the
   `claude -p` subprocess with `--permission-mode <mode>` and parses the
   stream-json envelope. Parser surfaces `permission_denials` on the
   terminal `event.session.result` frame and `permissionMode` on
   `event.session.init`.
2. **Backend** — `app/services/approval_service.py` owns the in-memory
   pending-approval store, the per-category timeout matrix, and the
   asyncio-future hand-off between bridge events and iOS WebSocket
   responses. Persistence is best-effort via `ApprovalRepository`.
3. **iOS** — receives the typed `question` WebSocket message, presents
   the approval sheet (T3.1 owns the UX), and POSTs the user's
   `approve` / `reject` decision back through `approval_response`
   WebSocket frame. Decision is dispatched by
   `app/api/routes/websocket.py` to
   `ApprovalService.submit_decision(...)`.

The runbook does **not** cover REST approval endpoints (none exist in V1
— decisions flow over the existing iOS WebSocket only) or sandboxing of
the subprocess itself (Bridge launchd plist hardening lives in T3.6).

---

## 2. Permission modes

The `--permission-mode` CLI flag is the primary lever. Backend RPC
payload (`apps/backend/app/orchestrator/claude_code_runner.py:290`) sets
`permission_mode = "acceptEdits"` for V1; the bridge falls back to
`config.toml` defaults if the field is empty. Per-request override wins
over config (`runner.go:237-248`).

| Mode               | Behaviour                                                                                              | When selected                                                                 |
|--------------------|--------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------|
| `acceptEdits`      | Edit/Write inside `cwd` auto-allow; Bash + Web tools still prompt; non-`cwd` writes deny + ask.        | **V1 default** for the lead session (Doc 10 §8 Faz 3 checklist + §9.7).       |
| `default`          | Every tool call denied → escalates to user via `permission_request` event.                             | Optional override for a session the user wants to chaperone explicitly.       |
| `plan`             | Read-only. No Edit, Write, Bash, or any state-mutating tool. Used by the planner subagent.             | Subagent spawn payload may set this when only Read/Glob/Grep/LS are needed.   |
| `skipPermissions`  | All tool calls auto-allow (claude CLI's "dangerous" mode).                                             | **NEVER use in production.** CI fixture / spike-only.                         |

**Subagent inheritance** — see §5.

---

## 3. Spike #5 fallback tree

Restated verbatim from Doc 10 §2.5 / §9.7. This is the **observed**
matrix the spike measured against the real claude CLI; the runbook
treats it as ground truth.

### 3.1 `acceptEdits`

- **Edit / Write inside `cwd`** — auto-allow. The Bridge runs the
  subprocess with `cwd = config.toml.project_dir` (or per-request
  override); claude considers any path **under** that directory safe.
- **Bash on whitelist** — auto-allow. Whitelist lives in claude's own
  config (`~/.claude/settings.json` `permissions.allow`); Doc 8 §3.2
  documents the canonical RafRaf whitelist (`ls`, `cat`, `pwd`, `git
  status`, `git diff`, `npm test`, `pytest`, …).
- **Bash off-whitelist** — deny + ask. Surfaces as a
  `permission_request` event the Bridge wraps and forwards.
- **Edit / Write outside `cwd`** — deny + ask. Same surface as
  off-whitelist Bash.

### 3.2 `default`

All tools deny → ask. Every tool call materialises an approval prompt.
Useful for paranoid sessions but expensive UX-wise.

### 3.3 `plan`

Read-only mode. claude CLI **silently refuses** Edit / Write / Bash —
the subagent falls back to text-only planning. No approval prompt fires
(the tool call never leaves the planner). Surfaced in
`event.session.result.permission_denials` as a `denied_silently`
record so the audit log still captures the attempt.

### 3.4 `skipPermissions`

Auto-allow everything. **Production guard** lives in the runner: the
backend RPC payload hard-codes `acceptEdits` and never forwards
`skipPermissions`. CI matrix occasionally exercises it for the bridge's
own integration tests (`apps/rafraf-bridge/internal/claude/runner_test.go`).

---

## 4. Tool risk classification

| Tool                              | Default mode (V1) | Risk    | Auto-allow | Prompt                        |
|-----------------------------------|-------------------|---------|------------|-------------------------------|
| Read / Glob / Grep / LS           | always            | low     | yes        | no                            |
| Edit / Write (inside `cwd`)       | acceptEdits       | medium  | yes        | only on denial                |
| Edit / Write (outside `cwd`)      | acceptEdits       | high    | no         | yes                           |
| Bash (whitelist)                  | acceptEdits       | medium  | yes        | no (whitelist hit)            |
| Bash (non-whitelist)              | acceptEdits       | high    | no         | yes                           |
| WebFetch / WebSearch              | any               | medium  | no         | yes                           |
| Task / Agent (spawn subagent)     | inherits          | varies  | inherits   | inherits (see §5)             |
| TodoWrite / NotebookEdit          | acceptEdits       | low     | yes        | no                            |

The `APPROVAL_MATRIX` in `app/schemas/approval.py` enumerates the
backend-side category mapping for tools the **iOS-side** orchestrator
can request (`docker_push`, `git_push`, `kubectl`, `aws_cli`, …). These
are distinct from the claude-CLI tool catalogue above; they fire the
same approval flow but originate from the orchestrator service rather
than from a stream-json `permission_request` envelope.

---

## 5. Subagent permission inheritance

Per Spike Test 2 + Test #5 (Doc 10 §2.2, §9.7):

- Subagent spawned via `Task` / `Agent` tool **inherits** the parent
  session's `permission_mode` unless the spawn payload explicitly
  overrides it. The bridge passes the parent's mode through unchanged.
- Override path: the parent's `Agent` tool input may carry a
  `permission_mode` field. When present, it wins for the duration of
  the subagent's lifetime only. The lead session keeps its original
  mode.
- Spike Test 2 fallback ordering (Doc 10 §9.7 Cases A/B/C):
  - **Case A — V1 chosen path** — dynamic inheritance + per-tool
    `permission_request` surfacing. iOS shows an approval sheet whenever
    the subagent's tool call falls outside the inherited allow-list.
  - **Case B — fallback** — statik denylist (write/bash/edit deny by
    default, user toggles open per-session). Wired in but **not
    activated** in V1.
  - **Case C — last resort** — claude plugin. Out of scope for V1.

Spike's empirical finding: V1 reliably hits Case A. Case B is the
escape hatch if a future claude release breaks the per-call denial
event surface.

---

## 6. Approval flow E2E

```
+------------+        +-----------+        +----------+        +-----+
|  claude -p | -----> |  Bridge   | -----> | Backend  | -----> | iOS |
| (Mac proc) |  SSE   | (Go)      |  WS    | (FastAPI)|  WS    |     |
+------------+        +-----------+        +----------+        +-----+
      ^                                          |                ^
      |                                          | submit_decision|
      | resume tool                              v                |
      |                              +----------------------+     |
      +------------------------------| ApprovalService      |<----+
                                     | (pending future map) |
                                     +----------------------+
```

Step-by-step:

1. **Bridge emits** — V1.1+V1.2+V1.3 closed the real-time path:
   the bridge's PreToolUse hook (`internal/cmd/rafraf-perm-hook`)
   intercepts every tool call before claude executes it, and the
   `permission.Broker` (`internal/permission/broker.go`) builds an
   `event.session.permission_request` envelope per
   `shared/api-contracts/ws/bridge-permission-messages.json` (schema
   carries `request_id`, `tool_name`, `tool_input`, `input_preview`,
   `risk`, `timeout_ms`, optional `parent_task_id`). The terminal
   `event.session.result.permission_denials` array is still emitted
   for the audit trail, but the real-time envelope is the canonical V1
   surface — see §11 closed gaps for the wave history.
2. **Backend dispatches** — `agent_ws.py` routes any envelope whose
   type starts with `event.` into `bridge_registry.dispatch_event(...)`
   keyed by `correlation_id`. The orchestrator-side runner is the
   subscriber; its `_dispatch_event` records the denial on the
   per-run state.
3. **ApprovalService.create_approval** — for orchestrator-initiated
   tools (`git_push`, `kubectl`, `docker_push`, …) the orchestrator
   calls `approval_service.create_approval(...)` directly. Returns an
   `ApprovalRequestRecord` with a UUID `id`, persists best-effort.
4. **iOS push** — `app/api/routes/websocket.py` builds a `question`
   WebSocket message via `ApprovalService.build_question_message(...)`
   and pushes it on the iOS-side `ConnectionManager` to the
   user's active session.
5. **User decision** — iOS sends `approval_response` over its
   WebSocket with `{approval_id, decision: "approved" | "rejected",
   note?}`. The websocket handler validates the payload (4 distinct
   error codes — see
   `apps/backend/tests/integration/test_websocket/test_ws_approval.py`) and calls
   `submit_decision(...)`.
6. **Decision propagation** — `submit_decision` resolves the asyncio
   future the orchestrator is awaiting in `wait_for_decision(...)`.
   Final state is written via `_process_decision`, which appends to
   `_history` and persists the `approved` / `rejected` status.
7. **Resume** — orchestrator returns control to the runner, which
   either issues the approved tool call to the bridge or aborts the
   session.

---

## 7. Timeout handling

- Default timeout: **300 s** for `DEPLOY` / `DESTRUCTIVE` /
  `INFRASTRUCTURE`, **180 s** for `WRITE_REMOTE` (per
  `CATEGORY_TIMEOUTS` in `app/schemas/approval.py:110-115`).
- Per-call override: `ApprovalRequestCreate.timeout_seconds` (only
  used when the category is unknown).
- Spike Test #5 baseline: 30 s. RafRaf chose longer windows because
  the iOS app may be backgrounded; the user gets a push notification
  first, then opens the app.
- On timeout: `_expire_approval` runs — pops the pending record,
  appends an `expired` history entry, persists `expired` status,
  and resolves the awaiter with `ApprovalResult(approved=False,
  decision="expired")`. This is the **deny-on-timeout**
  invariant — silence is never a yes.

For the **bridge-side** real-time `permission_request` flow (once
wired — see §11), the same deny-on-timeout invariant applies: when
the asyncio future expires, the backend sends a
`command.claude.permission.deny` envelope back to the bridge so the
running tool call can resolve.

---

## 8. Audit log

Every approval/denial is recorded:

- `ApprovalService` writes `ApprovalRequestRecord` rows to the
  `approvals` table (best-effort; failure logs `approval_db_persist_failed`
  but never raises). Status transitions update the same row.
- `AuditService.log_tool_call(...)` (`app/services/audit_service.py`)
  is called by the orchestrator when the **tool** (not the approval)
  finally executes, with `approval_required=True` and `approved_at`
  populated. The audit log row is the system-of-record for "did this
  user approve `kubectl apply` at 14:32".
- **Decision-time emit** — every `submit_decision` call site
  (`app/api/routes/websocket.py::_handle_approval_response`) now also
  invokes `AuditService.log_tool_call(approval_required=True,
  output_result={"decision": ...})` via the
  `_emit_approval_audit_log` helper. This means approval AND rejection
  decisions land in the audit log even when the tool never executes
  (rejected case). Best-effort — audit failure logs
  `approval_audit_log_emit_failed` but never breaks the WebSocket flow.
  Resolved 2026-05-02 (was wiring gap #4 in §11).
- For `permission_request` events from the bridge that never reach a
  decision (because the bridge rejected the tool itself), the denial
  appears on `ClaudeCodeResult.permission_denials`. The
  orchestrator forwards this to the audit log via
  `log_tool_call(success=False, error_message=denial.reason)`.

Audit log retention follows infra policy (Doc 10 §7); the runbook does
not duplicate.

---

## 9. Edge cases

### 9.1 Concurrent approvals (multiple subagents asking at once)

Each `ApprovalRequestRecord` carries a unique UUID `id`. The
`_pending` and `_waiters` dicts are keyed on this id, so N parallel
subagents requesting different approvals each block on their own
asyncio future without colliding. iOS sees multiple `question`
messages in flight; the approval sheet UI (T3.1) is responsible for
rendering a stack.

`ApprovalService.get_session_pending(session_id)` is a convenience
helper that returns the **first** pending record for a session — used
by debug endpoints, **not** in the hot path. It does not constrain the
number of concurrent approvals.

### 9.2 Approval during reconnect

If the iOS app disconnects while an approval is pending:

- The pending record stays in `_pending` and the asyncio future stays
  alive on the backend.
- On reconnect, `WebSocketReconnect` triggers a snapshot replay; the
  iOS client fetches outstanding approvals via
  `GET /approvals?status=pending` (REST endpoint TBD — currently the
  iOS side polls the WebSocket reconnect ack which carries pending
  approval IDs).
- If the user never reconnects, the timeout (§7) eventually fires
  and the deny-on-timeout invariant takes over.

### 9.3 Approval during rate-limit

When the bridge receives an `event.session.rate_limit` event, the
orchestrator's `on_rate_limit` callback fires. Pending approvals are
**not** invalidated — the user may still approve, but the resumed
tool call will hit the same rate-limit window and the bridge will
re-emit `rate_limit`. The backend's rate-limit middleware
(`app/middleware/rate_limit.py`, T2.4) surfaces `429` to iOS as a
typed `rate_limit_hit` event.

### 9.4 Bridge disconnect between request and decision

If the bridge disconnects after sending `permission_request` but
before the user decides:

- The decision is still recorded (audit log + history) when iOS
  responds.
- The orchestrator's `wait_for_decision(...)` returns normally.
- The follow-up `command.claude.permission.allow|deny` envelope sent
  to the bridge fails routing (`send_to_bridge` returns `False`),
  the runner raises `ClaudeCodeError`, the session ends with
  `is_error=True`. iOS sees a normal stream end with an error frame.

---

## 10. Production V1 default

**`permission_mode = "acceptEdits"` is the V1 default** (Doc 10 §8 Faz 3
checklist line 1460, hard-coded at
`apps/backend/app/orchestrator/claude_code_runner.py:290`).

Rationale:

1. **Mac local dev = trusted file system.** The bridge runs as the
   Mac user; the user already trusts claude to write to `cwd`. Asking
   on every Edit would push the UX over the friction cliff Spike Test
   #5 measured.
2. **Bash + Web still prompt.** The risky tools (Bash off-whitelist,
   WebFetch, WebSearch) still trigger approval, so the
   "convenient defaults + explicit consent for risky ops" balance
   matches the Doc 7 security analysis.
3. **Subagent inheritance.** Defaults must compose. `acceptEdits`
   propagating to subagents keeps planner / coder / reviewer subagent
   teams productive without per-tool prompts at every step (Spike Test
   #2 fallback Case A).
4. **Reversibility.** The flag is a single string in the RPC payload;
   tightening to `default` (deny everything) is one-line change away
   if a security incident demands it.

---

## 11. Wiring gaps surfaced (V1.1–V1.5 status)

These were identified during T3.2 test authoring. The V1.1–V1.5 wave
shipped **three of the four** end-to-end blockers; one item remains
deferred.

- ~~**Bridge → backend `permission_request` event.**~~
  **RESOLVED 2026-05-02 (V1.1 + V1.2 + V1.3).** The bridge now embeds
  a `PreToolUse` hook (Strategy B per design doc §2.1.1) that fires
  before any tool executes. The hook subprocess opens a UDS connection
  to the parent bridge process, the bridge's
  `permission.Broker.RequestDecision(...)`
  (`apps/rafraf-bridge/internal/permission/broker.go`) registers a
  waiter, classifies risk, and the runner's `wsEventSink.OnPermissionRequest`
  builds + emits the new `event.session.permission_request` envelope
  (schema documented in `shared/api-contracts/ws/bridge-permission-messages.json`).
  Touched by commits b9f2a4a (V1.1 protocol types + inbound channel),
  b329468 (V1.2 broker + UDS server + hook binary), 86dd472 (V1.3 broker → WS sink wiring).
  The runbook §6 step 1 caveat ("the bridge currently surfaces denials only on
  the terminal `event.session.result.permission_denials` array") is now
  **historical** — the real-time path is the canonical V1 surface.
- ~~**`command.claude.permission.allow|deny` RPC.**~~
  **RESOLVED 2026-05-02 (V1.1 + V1.3).** `ws.Client.Inbound` channel
  is wired (V1.1 — `apps/rafraf-bridge/internal/ws/client.go`),
  `runInboundDispatcher` routes typed envelopes into `dispatchCommand`
  (V1.1 — `apps/rafraf-bridge/cmd/bridge/main.go`), and the new
  `command.claude.permission.allow|deny` cases call
  `broker.Resolve(request_id, decision)` to unblock the matching UDS
  hook connection (V1.3). Schemas documented in
  `shared/api-contracts/ws/bridge-permission-messages.json`. The
  receiving runner is `_await_and_dispatch_decision` in
  `apps/backend/app/api/routes/websocket.py` (V1.4 commit 8a43991).
- **REST `GET /approvals?status=pending` snapshot replay.** Still
  deferred. Design doc §4.2 sketches the eventual flow; the iOS
  `WebSocketReconnect` coordinator currently does not re-fetch pending
  questions from the backend after reconnect, so a question pushed
  while the iOS app was background-suspended can be lost (the backend
  asyncio waiter is still alive — it eventually times out and denies,
  preserving the deny-on-timeout invariant). NOTE: V1.4 added
  `request_id`, `bridge_host_id`, `rpc_id` columns to the
  `approval_requests` table (migration 018) so future snapshot replay
  is implementable without further schema changes; the scope of
  remaining work is REST endpoint + iOS coordinator wiring.
  **Defer to V1.6+ or Faz 4.**
- ~~**`AuditService.log_tool_call` emit at `submit_decision` call site.**~~
  **RESOLVED 2026-05-02 (T3.2-followup + V1.4).** Originally wired in
  `app/api/routes/websocket.py::_handle_approval_response` via the
  `_emit_approval_audit_log` helper for the user-tap path. V1.4 added a
  **second** emit at the `_await_and_dispatch_decision` awaiter path
  so EVERY decision (user-tap, RFApprovalSheet timeout, bridge-offline
  dispatch failure) lands in `audit_log` with `approval_required=True`
  and `output_result={"decision": ...}`. Unit coverage in
  `tests/unit/test_api/test_websocket/test_handle_approval_response_audit.py`;
  contract anchor in
  `tests/integration/test_permission_flow.py::test_audit_log_records_each_decision`
  (xfail marker removed in V1.4 commit 8a43991).

---

## 12. Operator quick reference

```bash
# Inspect pending approvals (DB)
psql $DATABASE_URL -c "SELECT id, tool_name, action, category, status, timeout_at FROM approvals WHERE status = 'pending';"

# Inspect history (last 50)
psql $DATABASE_URL -c "SELECT tool_name, action, status, responded_at FROM approvals ORDER BY created_at DESC LIMIT 50;"

# Tail approval logs
kubectl logs -l app=rafraf-backend -f | grep -E 'approval_(created|processed|expired|decision_submitted)'

# Force-expire stale approvals (emergency)
# Run inside an admin shell — there is no UI surface for this.
psql $DATABASE_URL -c "UPDATE approvals SET status = 'expired' WHERE status = 'pending' AND timeout_at < NOW();"

# Inspect new V1.1+V1.4 permission counters
curl -s http://localhost:8000/metrics | grep -E '^permission_request_(emitted|decided|timeout)_total'
```

For runbook ownership transfer, file an issue with label
`runbook:permission-flow` and assign the Faz 3 squad lead.

---

## 13. End-to-end timeline

Per-hop latency budget for one permission_request → decision round-trip
(restated from `docs/design/v1-permission-blockers.md` §2.2.4 so SREs
can size alerts without bouncing between docs).

| Hop                                                  | Budget                       |
|------------------------------------------------------|------------------------------|
| Hook subprocess fork + UDS connect                   | ≤ 50 ms                      |
| Bridge → backend WS frame                            | ≤ 30 ms (LAN) / ≤ 200 ms (cross-region) |
| Backend forward to iOS                               | ≤ 50 ms                      |
| **User decision (RFApprovalSheet auto-timeout)**     | up to 30 s                   |
| iOS → backend WS frame                               | ≤ 200 ms                     |
| Backend → bridge WS frame                            | ≤ 30 ms                      |
| Bridge → hook UDS write + hook stdout flush          | ≤ 50 ms                      |
| **Total worst case**                                 | **~30.6 s**                  |

Claude CLI's PreToolUse hook timeout is 60 s by default, so the V1
budget leaves a 2× safety margin. The bridge-suggested `timeout_ms`
field on `event.session.permission_request` (default `30000`) is the
hard ceiling propagated to all layers:

| Layer                              | Effective ceiling                         |
|------------------------------------|-------------------------------------------|
| iOS RFApprovalSheet countdown      | `request.timeoutSeconds` (= 30 s)         |
| Backend ApprovalService awaiter    | `bridge_timeout_seconds + 2 s` grace      |
| Bridge UDS broker timeout          | `timeout_ms + 4 s` grace                  |
| Claude CLI hook timeout (CLI)      | 60 s default — left untouched             |

Operators alerting on `permission_request_round_trip_seconds` should
fire warning at p95 > 5 s and page at p95 > 25 s (= within budget but
approaching auto-deny). The matching Prometheus counter catalogue
(emitted / decided / timeout) lives in `infra/grafana/README.md`.

---

## 14. Manual smoke test

Step-by-step recipe for a developer to verify the entire permission
loop on their Mac. Assumes a working local backend stack and an iOS
simulator. Run in order; each step has an explicit pass criterion.

1. **Build the bridge + hook binary.**
   ```bash
   cd apps/rafraf-bridge
   make build
   ```
   Pass criterion: `bin/rafraf-bridge` and `bin/rafraf-perm-hook`
   exist (~2.6 MiB each on darwin-arm64).

2. **Start the backend dev stack.**
   ```bash
   docker compose -f infra/docker/docker-compose.dev.yml up -d
   cd apps/backend && python -m uvicorn app.main:app --reload
   ```
   Pass criterion: `curl http://localhost:8000/health` returns 200.

3. **Pair the bridge with backend.**
   ```bash
   ./apps/rafraf-bridge/bin/rafraf-bridge \
     -config ~/.config/rafraf-bridge/config.toml
   ```
   Pass criterion: bridge logs `bridge_paired host_id=...` and
   backend logs `agent_register host_id=...`. The
   `event.session.permission_request` envelope cannot fire until the
   inbound channel handshakes are complete.

4. **Open the iOS app in the simulator.**
   - Launch from Xcode (`apps/ios/RafRaf` scheme).
   - Log in with a dev JWT (or run through the onboarding flow).
   - Tap into a fresh chat session.

   Pass criterion: WebSocket connection indicator shows green.

5. **Issue a prompt that should trigger a permission prompt.**
   In the iOS chat input field, send:
   ```
   Lütfen tmp/build.log dosyasını sil
   ```
   (Or any prompt that drives claude to call `Bash` with an
   off-whitelist command — `rm`, `curl https://...`, `git push`.)

   Pass criterion: bridge logs
   `permission_request_emit request_id=... tool=Bash risk=high`.

6. **Verify the iOS sheet renders correctly.**
   The `RFApprovalSheet` should appear within ~1 s of step 5,
   showing:
   - **Risk badge**: `risk=high` (red).
   - **Countdown timer**: 30 s.
   - **Three buttons**: "İzin Ver (tek seferlik)",
     "İzin Ver (oturum)", "Reddet".
   - **Tool context line**: `Tool: Bash, Action: rm -rf tmp/build.log`
     (or similar 240-byte preview).

   Pass criterion: sheet matches all four checks above. If countdown
   reads anything other than 30 s, the bridge `timeout_ms`
   propagation is broken — see §13 ceiling table.

7. **Reject path — tap "Reddet".**
   - Expected: claude reports refusal in the result event ("Tool
     çağrısı reddedildi" or similar).
   - Verify the audit log row exists:
     ```sql
     SELECT id, tool_name, action, output_result FROM audit_log
       WHERE approval_required = TRUE
       ORDER BY created_at DESC LIMIT 1;
     ```
   - Expected: `output_result->>'decision' = 'rejected'`.

   Pass criterion: refusal text appears in iOS chat AND audit row
   exists with `decision = 'rejected'`.

8. **Allow-session path — issue another prompt that triggers the
   same tool, tap "İzin Ver (oturum)".**
   - Expected: claude continues, completes the tool call, and the
     subsequent message renders normally.
   - **V1 caveat**: the backend currently treats `allow_session` as
     `allow_once` (the wire only knows "approved" / "rejected"; the
     `note: "allow_session"` is captured but not yet used for
     deduplication). A second invocation of the same tool in the
     same session WILL prompt again. Full session-allow ships in
     Faz 4 per design doc §6.3.

   Pass criterion: tool executes successfully on this turn AND a
   second invocation in the same session re-prompts (expected V1
   behaviour). Audit row for this turn carries
   `output_result->>'decision' = 'approved'`.

9. **Timeout path — issue another triggering prompt and DO NOT tap
   anything for 30 s.**
   - Expected: sheet auto-dismisses at 0 s; iOS sends
     `approval_response{decision: "rejected"}` automatically; backend
     dispatches `command.claude.permission.deny` with
     `reason: "timeout"`; bridge broker resolves the hook with
     `block`; claude reports refusal.
   - Verify the metric:
     ```bash
     curl -s http://localhost:8000/metrics | grep permission_request_timeout_total
     ```
   - Expected: counter incremented by 1 with
     `tool_name="Bash"`.

   Pass criterion: refusal text in iOS AND timeout counter
   incremented AND audit row carries
   `output_result->>'decision' = 'expired'` or `'rejected'`
   (acceptable either way — both indicate auto-deny took effect).

10. **Cleanup.**
    Stop the bridge with `Ctrl+C`. Verify
    `$TMPDIR/rafraf-bridge-perm-*.sock` and
    `$TMPDIR/rafraf-bridge-settings-*.json` are removed (best-effort
    cleanup; a startup sweep handles leaks > 1 h old).

If any step fails, capture bridge logs (`-log-level debug`) + backend
logs + the relevant `audit_log` row and file an incident with label
`runbook:permission-flow`.
