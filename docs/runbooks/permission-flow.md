# Permission Flow Runbook

> Bridge → backend → iOS approval cycle for claude tool calls. Codifies
> Spike Test #5's fallback tree (Doc 10 §2.5, §9.7) and the V1 default
> `permission_mode = acceptEdits`.

| Field          | Value                                      |
|----------------|--------------------------------------------|
| Owner          | Backend / Faz 3 squad                      |
| Last Reviewed  | 2026-05-02 (Faz 3 — T3.2)                  |
| Related Specs  | Doc 10 §2.5, §6.1, §9.7; Doc 11 §5; Doc 7 |
| Source of Truth| `apps/backend/app/services/approval_service.py`, `apps/rafraf-bridge/internal/claude/runner.go` |

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

1. **Bridge emits** — claude CLI's stream-json contains a tool call the
   permission policy denies. Parser packs the denial into the per-frame
   subagent state (`apps/rafraf-bridge/internal/claude/state.go:190`)
   and a `permission_request` envelope is sent over the bridge's
   WebSocket. (For V1, the bridge currently surfaces denials only on
   the **terminal** `event.session.result.permission_denials` array;
   per-tool real-time `permission_request` event surfacing is the
   gap noted in §11 below.)
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

## 11. Wiring gaps surfaced (deferred)

These were identified during T3.2 test authoring; they are **not**
fixed in T3.2 (per the task scope). Tracked for follow-up:

- **Bridge → backend `permission_request` event.** Today the bridge
  surfaces denials only on the terminal
  `event.session.result.permission_denials` array (see
  `parser.go:594` — `PermissionDenials` field on the `handleResult`
  result struct). Real-time per-tool `permission_request` envelope
  surfacing (so iOS gets the prompt **before** the run completes) is
  not yet wired. Approval flow §6 step 1 documents the eventual path;
  the integration tests in `tests/integration/test_permission_flow.py`
  exercise the orchestrator-direct path
  (`approval_service.create_approval(...)`) which is the V1 surface
  area. Tracked as `T3.2-followup-bridge-perm-event`.
- **`command.claude.permission.allow|deny` RPC.** Backend can record
  decisions but lacks an envelope to push them back into a live
  bridge-side claude run. Same follow-up.
- **REST `GET /approvals?status=pending`.** Reconnect snapshot
  currently piggy-backs on the WebSocket ack; a typed REST endpoint
  would simplify iOS reconnect logic.
- **`AuditService.log_tool_call` emit at `submit_decision` call site.**
  Wire `AuditService.log_tool_call(approval_required=True,
  output_result={"decision": ...})` at the `submit_decision` call site
  so approval decisions appear in the audit log alongside tool
  execution events. Today the audit log only sees the *tool* row when
  it eventually executes (§8 first bullet); the decision itself —
  including `rejected` decisions where no tool runs — is recorded only
  in `_history`. The integration test
  `test_audit_log_records_each_decision` is `xfail`-marked against
  this gap and pins the intended contract.

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
```

For runbook ownership transfer, file an issue with label
`runbook:permission-flow` and assign the Faz 3 squad lead.
