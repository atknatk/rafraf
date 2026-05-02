# V1 Permission Blockers — Design + Dispatch Plan

> **Status**: Design accepted; awaiting user greenlight for V1.1..V1.7 dispatch.
> **Author**: Plan agent (post-Sync-4 / Session 5).
> **Date**: 2026-05-02.
> **Branch**: `feature/f3/testflight-launch` @ 4ab9706.

## 0. Executive context

**Phase**: Pre-Wave-2 (Wave 1 done: iOS UI polish + Helm + runbooks). Wave 2 (TestFlight build) waits on user with Mac + Apple Developer creds.

**These two blockers must land *before* Wave 2** so the very first TestFlight binary already exhibits the correct pre-action approval UX.

The two blockers are tightly coupled: Blocker A is the *outbound leg* (bridge → backend → iOS) and Blocker B is the *inbound leg* (iOS → backend → bridge → claude). Without B, A would only let users *know* about a pending tool call but not *answer* it. We therefore ship them together as one feature slice with a single contract negotiation.

---

## 1. Current state (verified by code reading)

### 1.1 Bridge — `apps/rafraf-bridge/`

The bridge is a Go daemon that owns a `claude -p --output-format stream-json --include-partial-messages --permission-mode <mode>` subprocess (`internal/claude/runner.go:280-299`). Its `Parser` (`internal/claude/parser.go:128-167`) decodes one NDJSON frame per line and dispatches to typed `EventSink` callbacks for **11 event subtypes** today:

| Stream-json `type[/subtype]` | EventSink callback | Envelope `type` constant |
|---|---|---|
| `system/init` | `OnInit` | `event.session.init` |
| `system/task_started` | `OnTaskStarted` | `event.session.task_started` |
| `system/task_progress` | `OnTaskProgress` | `event.session.task_progress` |
| `system/task_notification` | `OnTaskNotification` | `event.session.task_notification` |
| `system/hook_started` | `OnHookStarted` | `event.session.hook_started` |
| `system/hook_response` | `OnHookResponse` | `event.session.hook_response` |
| `system/status` | (logged only) | — |
| `assistant` | `OnAssistant` | `event.session.assistant` |
| `user` | `OnUser` | `event.session.user` |
| `stream_event` | `OnStream` | `event.session.stream` |
| `rate_limit_event` | `OnRateLimit` | `event.session.rate_limit` |
| `result` | `OnResult` | `event.session.result` |

Crucially, there is **no real-time `permission_request` envelope**. Permission denials are surfaced **only** on the terminal `result` frame via `EventSessionResult.PermissionDenials []json.RawMessage` (`parser.go:585-633`, `messages.go:166-176`).

The empirical evidence in `internal/claude/testdata/02-agent-teams.jsonl` (lines 263, 287, 308, 311, 314, 322, 330, 361, 391, 394, 412, 420, 445, 453, 478) shows the CLI's actual surface: when a tool call is denied, the next frame is a `user`-role `tool_result` with `is_error: true` and content like `"Claude requested permissions to write to /path/to/file, but you haven't granted it yet."` This is **post-hoc**, attached to a tool_use that already happened. The CLI does not emit a separate `permission_request` event in this mode.

The bridge exposes outbound RPC but **cannot currently receive inbound commands beyond the wiring stub**: `runInboundDispatcher` (`cmd/bridge/main.go:336-344`) is a placeholder that selects only on `<-ctx.Done()`; the actual `ws.Client` reader goroutine (`internal/ws/client.go:118-127`) drains inbound frames into `/dev/null` to keep the socket alive. The `dispatchCommand` switch (`cmd/bridge/main.go:350-394`) is wired for `command.claude.run` and `command.claude.abort` but never invoked. **The bridge has no `Inbound chan protocol.Envelope` channel.**

The runner's CLI argument vector (`runner.go:280-299`) constructs:
```
claude -p --output-format stream-json --verbose --include-partial-messages [--permission-mode <mode>] [--resume <id>] <prompt>
```
It does **not** pass `--permission-prompt-tool` (the CLI flag that would route permission decisions through an MCP-server tool the bridge could host). It does **not** pre-populate `~/.claude/settings.json permissions.allow` per-request. Every spawn is a plain stdio subprocess.

### 1.2 Backend — `apps/backend/app/`

Two WSS endpoints:
- **`/ws/agent`** (`api/routes/agent_ws.py`) — bridge-side. Auths via shared secret API key (line 125, deprecated until T1.x bridge pairing). On `agent_register` it stores `host_id → connection_id`. The generic `event.*` branch (line 200-204) routes any envelope whose `type` starts with `event.` to `bridge_registry.dispatch_event(...)`. Anything else is logged as `agent_ws_unknown_message`.
- **`/ws`** (`api/routes/websocket.py`) — iOS-side. Auths via JWT. Owns `MessageType` switch including `APPROVAL_RESPONSE` (line 236). `_handle_approval_response` (line 910-987) decodes `{approval_id, decision, note?}`, builds `ApprovalDecision`, calls `approval_service.submit_decision(...)`. If that returns `False` (no waiter), it falls through to `question_bridge.submit_answer(...)`. If both miss it sends `APPROVAL_NOT_FOUND` error.

The orchestrator runner (`orchestrator/claude_code_runner.py`) sends `command.claude.run` envelopes pinning `permission_mode = "acceptEdits"` (line 381). Its `_dispatch_event_inner` (line 553-791) handles 9 of the 11 bridge event types. Result events surface `permission_denials` onto `state.permission_denials` (line 708-710) and into the returned `ClaudeCodeResult` (line 480). **Nothing in the runner today opens a question to iOS for a tool call** — `on_question` callback exists (line 241) but is only invoked through `QuestionBridge.ask_user` and only for the `AskUserQuestion` claude tool (separate code path, not for permissions).

`ApprovalService` (`services/approval_service.py`) is the in-memory pending-approval store. `create_approval` returns a `PENDING` record + persists best-effort via `ApprovalRepository`. `wait_for_decision(approval_id)` blocks on an asyncio Future with a per-category timeout (180s for WRITE_REMOTE, 300s for the other 3). `submit_decision` resolves the future. `_expire_approval` is the deny-on-timeout path. `build_question_message` constructs the iOS-bound `MessageType.QUESTION` envelope (`approval_service.py:379-415`).

`BridgeRegistryService.send_to_bridge(host_id, envelope)` (`services/bridge_registry_service.py:384-421`) is the **outbound primitive** the new RPC will reuse: it looks up the bridge connection_id via `agent_manager` and calls `send_json`. It returns `False` cleanly if the bridge is offline.

`BridgeRegistryService.dispatch_event` (line 543-590) routes inbound envelopes by `correlation_id`, **silently dropping correlation-less events**. This is important: the new `permission_request` envelope MUST carry the `command.claude.run` correlation_id (= `rpc_id`) so it lands in the runner's per-RPC subscriber queue.

### 1.3 iOS — `apps/ios/RafRaf/`

Approval UI is fully built (T3.1):
- `RFApprovalSheet` (`Features/Approval/Presentation/Views/RFApprovalSheet.swift`) — modal sheet with risk badge, countdown timer, three buttons (Allow once / Allow session / Deny), 30s auto-deny default.
- `RFApprovalCard` — legacy inline card view (older approval surface, still in tree).
- `ApprovalCardViewModel` (`Features/Approval/Presentation/ViewModels/ApprovalCardViewModel.swift`) — Observable state machine that drives `RFApprovalCard` and houses the countdown logic + decision dispatch.
- `ApprovalQuestion` (`Features/Approval/Domain/Models/ApprovalQuestion.swift`) — domain model.
- `ApprovalQuestionDTO` (`Features/Approval/Data/DTOs/ApprovalQuestionDTO.swift`) — wire model.
- `ApprovalRepositoryImpl.submitDecision(...)` (`Features/Approval/Data/Repositories/ApprovalRepositoryImpl.swift:19-50`) — sends `approval_response` over the iOS WSS.

**Critical gap**: `WebSocketMessageType` enum (`Core/Networking/WebSocketMessage.swift:15-51`) has **no `case question`** and **no `case approvalRequest`**. The `WebSocketBaseMessage.init(from:)` decoder switches on the type string (lines 79-200ish) but never matches `"question"`. This means **the inbound `question` envelope the backend already sends today is silently dropped on iOS**. The `RFApprovalCard` UI works only via SwiftUI previews and the legacy in-app trigger paths; there is no live code path that takes a real backend `question` message to the screen. (This is a pre-existing latent bug; making it work is part of Blocker A.)

### 1.4 Shared contracts

`shared/api-contracts/ws/approval-messages.json` defines `question` (server→client) and `approval_response` (client→server). It does **not** define a separate `permission_request` envelope. We can either add a new envelope to this contract or reuse `question` — see §2.1.5.

---

## 2. Gap analysis

### 2.1 Gap A: real-time `permission_request` envelope (bridge → backend → iOS)

#### 2.1.1 What claude CLI actually emits when permission is needed

Two empirically-verified surfaces, neither of which is a clean "ask first" event:

1. **Plain `--permission-mode default` mode**: The CLI executes the `tool_use`, immediately denies it internally, and emits a `user`-role `tool_result` with `is_error: true` and content `"Claude requested permissions to <verb> to <path>, but you haven't granted it yet."` (verified in `testdata/02-agent-teams.jsonl`). The denial also accumulates into the terminal `result.permission_denials` array. **No frame is emitted before the tool_use that says "I am about to call X — may I?"**

2. **`--permission-prompt-tool <tool_name>` mode** (CLI flag, not currently used by the bridge): Routes every permission decision through an MCP server tool the host hosts. This *is* the pre-action interception path the spec assumes — the MCP tool receives the `tool_name + tool_input` and returns `{behavior: "allow"|"deny", message?, updatedInput?}` to the CLI. The bridge does not currently embed an MCP server.

The runbook §11 names the "real-time `permission_request` envelope" explicitly. Two implementation strategies satisfy it:

- **Strategy A (intercept post-hoc)**: Detect the `tool_result.is_error == true` denial frames in the `user` event handler, lift them to a synthesised `permission_request` envelope, then *replay* the tool call upon approval. Cannot replay reliably (the parent `tool_use` already executed and the model has moved on). **Rejected** — this is the current "yaptın işte" UX the user is complaining about.

- **Strategy B (intercept pre-action via PreToolUse hook)**: Configure claude CLI to invoke a `PreToolUse` hook script that the bridge ships. The hook runs synchronously, blocks the tool call until it returns, and prints a JSON decision to stdout. The hook implementation is a tiny Go binary (or a shell shim) that opens a Unix-domain socket back to the parent bridge process, sends the pending tool_use payload, blocks on a reply, then writes `{"decision": "allow"|"block", "reason"?}` to stdout. The bridge meanwhile forwards the envelope to backend → iOS, awaits the user, and pushes the answer back through the UDS to the hook. **Recommended.**

- **Strategy C (intercept pre-action via `--permission-prompt-tool`)**: Embed a lightweight MCP server in the bridge process and pass `--permission-prompt-tool rafraf_approval`. Functionally equivalent to Strategy B but heavier (requires MCP server lifecycle inside the bridge). Defer — the PreToolUse hook is simpler and has been used productively by the spike.

We adopt **Strategy B**. The hook script is a thin shim; the bridge is the actual decision-maker.

#### 2.1.2 What needs to change in the bridge

1. **New `internal/permission/` package**:
   - `Broker` struct that owns:
     - A `map[toolUseID]chan Decision` for in-flight requests.
     - A Unix-domain socket listener (path: `$TMPDIR/rafraf-bridge-perm.sock`, mode 0600, per-bridge-process).
     - A `RequestDecision(ctx, sessionID, toolName, toolInput) (Decision, error)` method that registers a waiter, fires the outbound envelope via the EventSink, and blocks on the channel with a context-bounded timeout.
   - `Decision` enum: `Allow | Deny | Expired`.

2. **New EventSink callback** `OnPermissionRequest(ev protocol.EventPermissionRequest) error` (added to `claude.EventSink` in `internal/claude/runner.go:122-134`). The runner's `wsEventSink` adapter (`cmd/bridge/main.go:404-466`) gets a matching method that builds + sends `event.session.permission_request`.

3. **Hook script**: a small Go binary at `internal/cmd/rafraf-perm-hook/main.go` (or shipped as an embedded shell script). Reads the PreToolUse JSON envelope from stdin, opens the UDS, writes `{tool_use_id, tool_name, tool_input, session_id}`, blocks on a JSON reply, prints `{"decision": "allow"}` or `{"decision": "block", "reason": "user denied"}` to stdout, exits 0. The CLI documentation for hooks specifies that a PreToolUse hook printing `{"decision": "block"}` cancels the tool call.

4. **Settings injection**: Bridge writes a per-session `~/.claude/settings.json` overlay (or appends a per-request `--settings <file>` arg) that registers:
   ```json
   {
     "hooks": {
       "PreToolUse": [
         { "matcher": ".*", "hooks": [{ "type": "command", "command": "<bridge-prefix>/rafraf-perm-hook" }] }
       ]
     }
   }
   ```
   The matcher `.*` fires on every tool. The hook shells out to the bridge UDS for the actual decision. We choose the per-request overlay path so the user's normal `~/.claude/settings.json` is untouched.

5. **PermissionMode change**: With the hook installed, the bridge can keep `permission_mode = acceptEdits` (so Read/Glob/Grep stay frictionless) and let the hook adjudicate Edit/Write/Bash on top. Alternatively, switch to `default` (deny everything → escalate to hook). Recommendation: keep `acceptEdits` for the lead session and let the hook only fire when the CLI's own policy denies. This minimises the user's tap count.

#### 2.1.3 New WSS envelope schema (bridge → backend, then backend → iOS)

Add a new envelope type to `apps/rafraf-bridge/internal/protocol/messages.go`:

```go
const TypeEventSessionPermissionRequest = "event.session.permission_request"

type EventSessionPermissionRequest struct {
    SessionID    string          `json:"session_id"`
    RequestID    string          `json:"request_id"`        // bridge-generated UUID; backend echoes
    ToolName     string          `json:"tool_name"`         // canonical (post-aliased)
    ToolInput    json.RawMessage `json:"tool_input"`        // verbatim from claude
    InputPreview string          `json:"input_preview"`     // 240-byte truncated text for iOS
    Risk         string          `json:"risk"`              // low|medium|high (computed by bridge)
    Reason       string          `json:"reason,omitempty"`  // why approval was needed (whitelist miss, off-cwd write, …)
    TimeoutMs    int             `json:"timeout_ms"`        // bridge-suggested timeout (default 30000)
    ParentTaskID string          `json:"parent_task_id,omitempty"` // when emitted from a subagent
}
```

`request_id` is bridge-generated and is the **decision correlation token** Blocker B uses. The envelope's outer `correlation_id` carries the `command.claude.run` rpc_id (so backend dispatch routes it into the right subscriber queue).

Risk classification table (in bridge):
| Tool | Default risk |
|---|---|
| `Read`, `Glob`, `Grep`, `LS`, `TodoWrite`, `NotebookEdit` | low |
| `Edit`, `Write` (within cwd) | medium |
| `Edit`, `Write` (outside cwd), `Bash` (whitelist hit) | medium |
| `Bash` (off-whitelist), `WebFetch`, `WebSearch` | high |
| Unknown / MCP / plugin tools | high (deny-default) |

Backend translates `EventSessionPermissionRequest` → existing `MessageType.QUESTION` payload to iOS, mapping `request_id → approval_id`, `tool_name → context`, `input_preview → question text + context`, `risk → category` (high → DESTRUCTIVE, medium → WRITE_REMOTE, low → fallback). This **reuses the existing iOS contract** and minimises iOS-side schema churn.

#### 2.1.4 Backend handler additions

In `apps/backend/app/orchestrator/claude_code_runner.py::_dispatch_event_inner`, add a new branch:

```python
if event_type == "event.session.permission_request":
    request_id = str(payload.get("request_id", ""))
    tool_name = str(payload.get("tool_name", ""))
    risk = str(payload.get("risk", "high"))
    # Map to ApprovalCategory.
    category = {"high": DESTRUCTIVE, "medium": WRITE_REMOTE, "low": INFRASTRUCTURE}.get(risk, DESTRUCTIVE)
    # Build ApprovalRequestCreate, call approval_service.create_approval(...).
    # Push QUESTION message to iOS via on_question callback (or directly via ConnectionManager).
    # Spawn an asyncio.Task that awaits wait_for_decision(approval_id) and on resolve sends
    # command.claude.permission.allow|deny to the bridge via send_to_bridge.
    return False  # NOT terminal; the result event still comes
```

The decision-await task must be **fire-and-forget** so the runner's stream loop isn't blocked. The runner loop must keep consuming further bridge events (additional permission_request frames may arrive concurrently for parallel subagents).

Add `on_permission_request: PermissionRequestCallback` to the runner's optional callbacks so `websocket.py::_process_with_orchestrator` can push the question to the active iOS connection without going through `QuestionBridge` (which is `AskUserQuestion`-only).

#### 2.1.5 iOS receiver additions

1. Extend `WebSocketMessageType` (`apps/ios/RafRaf/Core/Networking/WebSocketMessage.swift:15-51`) with `case question = "question"`.
2. Add a `QuestionContent` case to `WebSocketContent` enum and decode into `ApprovalQuestionDTO` inside `WebSocketBaseMessage.init(from:)`.
3. Add a `WebSocketMessageRouter` handler that takes the decoded `ApprovalQuestion` and calls a singleton `ApprovalCoordinator.present(question:)` (new file).
4. `ApprovalCoordinator` (new) bridges the inbound question to either `RFApprovalSheet` (preferred for new UX) or the legacy `ApprovalCardViewModel.showQuestion(_:)`. It resolves to a single shared `@Observable` state holder that the root view (`ContentView` or `HomeView`) renders as a `.sheet(item: $coordinator.activeQuestion)`.
5. Decision routing already exists via `ApprovalRepositoryImpl.submitDecision(...)`. No changes there.

### 2.2 Gap B: decision RPC (backend → bridge → claude)

#### 2.2.1 How claude consumes the answer

With Strategy B (PreToolUse hook), the answer is delivered **back through the hook's UDS connection to the bridge, then printed to stdout**. The hook stays blocked on a UDS read until the bridge writes the JSON reply; once the reply arrives, the hook prints the appropriate `{"decision": ...}` JSON and exits, which unblocks the CLI's tool execution.

This means the bridge needs:
1. A UDS server inside `internal/permission/Broker` that pairs each connection to a `request_id` (sent in the first hook→bridge frame).
2. A `Resolve(requestID, decision)` method that finds the matching open UDS connection and writes the reply.
3. A timeout: if no decision arrives within `TimeoutMs`, the broker writes `{"decision": "block", "reason": "timeout"}` and the hook reports denial back to claude. This preserves the deny-on-timeout invariant.

#### 2.2.2 Bridge RPC handler for `command.claude.permission.allow|deny`

Add to `apps/rafraf-bridge/internal/protocol/messages.go`:

```go
const (
    TypeCommandClaudePermissionAllow = "command.claude.permission.allow"
    TypeCommandClaudePermissionDeny  = "command.claude.permission.deny"
)

type CommandClaudePermissionDecision struct {
    SessionID   string  `json:"session_id"`
    RequestID   string  `json:"request_id"`
    Decision    string  `json:"decision"`              // "allow" | "deny"
    Reason      string  `json:"reason,omitempty"`
    UpdatedInput json.RawMessage `json:"updated_input,omitempty"` // optional MCP-style edit; ignored for V1
}
```

In `cmd/bridge/main.go::dispatchCommand`, add cases for both new types that look up the broker (now a process-wide singleton or DI-injected dependency) and call `broker.Resolve(requestID, decision)`.

This requires the bridge to have a working **inbound channel** — which today is the placeholder `runInboundDispatcher`. So Blocker B implicitly forces wiring `ws.Client.Inbound chan protocol.Envelope` and replacing the discard reader with a fan-out into that channel. **This is the highest-leverage piece of plumbing in the whole design** — once it exists, future inbound RPCs (cancel, status query, future bridge admin commands) come for free.

#### 2.2.3 Backend dispatch from RFApprovalSheet decision

`websocket.py::_handle_approval_response` already drives `approval_service.submit_decision(...)`. We need to attach an `on_decision` follow-through that:
1. Looks up the originating `permission_request` by `approval_id` (= `request_id`).
2. Identifies the bridge `host_id` (via the originating RPC's correlation_id → already known by the runner).
3. Calls `bridge_registry.send_to_bridge(host_id, envelope)` with type `command.claude.permission.allow` or `command.claude.permission.deny`.

Cleanest implementation: the runner's permission-request branch (§2.1.4) installs an asyncio task that awaits `approval_service.wait_for_decision(approval_id)` and **owns the round-trip** itself. So the iOS `submit_decision` resolves the future, and the same coroutine that registered the waiter is the one that pushes the bridge envelope. This keeps state local to the runner.

#### 2.2.4 Latency budget

End-to-end timing per round-trip (well under claude's internal hook timeout):

| Hop | Budget |
|---|---|
| Hook subprocess fork + UDS connect | ≤ 50 ms |
| Bridge → backend WS frame | ≤ 30 ms (LAN) / ≤ 200 ms (cross-region) |
| Backend forward to iOS | ≤ 50 ms |
| **User decision (RFApprovalSheet auto-timeout)** | up to 30 s |
| iOS → backend WS frame | ≤ 200 ms |
| Backend → bridge WS frame | ≤ 30 ms |
| Bridge → hook UDS write + hook stdout flush | ≤ 50 ms |
| **Total worst case** | ~30.6 s |

Claude CLI's PreToolUse hook timeout is 60 s by default. **We are within budget by a factor of 2.** The bridge-suggested `TimeoutMs` field on `permission_request` (default 30 000) is the hard ceiling we communicate to all layers. iOS RFApprovalSheet's countdown should equal this value; backend `ApprovalService` timeout should equal this value + 2 s grace; bridge UDS broker timeout should equal this value + 4 s grace; claude CLI hook timeout should be left at 60 s default.

**Critical constraint**: The runner's `stream_events` async iterator MUST keep running while we await the decision. The current design (§2.1.4) handles this because the await is fire-and-forget on a separate Task.

---

## 3. Detailed task breakdown — proposed agent dispatch plan

### V1.1 — Wire bridge inbound channel + extend protocol catalogue

**Title**: Bridge inbound RPC plumbing + permission protocol types
**Files to touch**:
- `apps/rafraf-bridge/internal/ws/client.go` — add `Inbound chan protocol.Envelope` (capacity 64); replace `_, _, err := conn.Read(...)` discard with `_, data, err := conn.Read(...); var env protocol.Envelope; if err := json.Unmarshal(data, &env); err == nil { c.Inbound <- env }`.
- `apps/rafraf-bridge/internal/protocol/messages.go` — add `TypeEventSessionPermissionRequest`, `TypeCommandClaudePermissionAllow`, `TypeCommandClaudePermissionDeny`, plus the `EventSessionPermissionRequest` and `CommandClaudePermissionDecision` structs.
- `apps/rafraf-bridge/internal/protocol/builder.go` — add `NewEventSessionPermissionRequest`, `NewCommandClaudePermissionAllow`, `NewCommandClaudePermissionDeny`.
- `apps/rafraf-bridge/internal/protocol/envelope_test.go` — add round-trip tests.
- `apps/rafraf-bridge/cmd/bridge/main.go::runInboundDispatcher` — replace the placeholder body with `for { select { case <-ctx.Done(): return; case env := <-wsClient.Inbound: dispatchCommand(ctx, runner, wsClient, logger, env) } }`.

**Tests required**: Go unit tests for the new envelope round-trips; an integration test using `httptest` that posts a `command.claude.permission.deny` envelope and asserts the dispatcher receives it.

**Estimated complexity**: M (touches three packages, but the changes per package are mechanical).

**Dependencies**: none. This is the foundation.

**Agent type**: general-purpose (Go-savvy).

**Critical risks**:
- Backpressure: an unbounded inbound channel could OOM if a client floods commands. Cap at 64 + log + drop on overflow.
- JSON decode errors must not kill the reader goroutine; log warning and continue.

---

### V1.2 — Bridge permission Broker + UDS server + hook binary

**Title**: PreToolUse hook + UDS broker for synchronous permission decisions
**Files to touch**:
- `apps/rafraf-bridge/internal/permission/broker.go` (new) — owns the UDS listener, in-flight `map[requestID]chan Decision`, `RequestDecision(ctx, sessionID, toolName, toolInput) (Decision, error)`, `Resolve(requestID, decision Decision)`.
- `apps/rafraf-bridge/internal/permission/broker_test.go` (new).
- `apps/rafraf-bridge/internal/permission/risk.go` (new) — risk-classification table (matches `_TOOL_DISPLAY_NAMES` keys in Python and the Doc 11 §6 catalogue).
- `apps/rafraf-bridge/internal/cmd/rafraf-perm-hook/main.go` (new) — the small CLI binary. Reads stdin JSON, dials the UDS at `$RAFRAF_BRIDGE_PERM_SOCK`, writes the request, reads reply, prints decision, exits.
- `apps/rafraf-bridge/internal/claude/runner.go::buildArgs` — add `--settings <file>` pointing at a per-session generated overlay.
- `apps/rafraf-bridge/internal/claude/runner.go::Run` — write the settings overlay to `$TMPDIR/rafraf-bridge-settings-<uuid>.json` before spawn, defer-cleanup.
- `apps/rafraf-bridge/Makefile` / build script — add hook binary to release artifacts and `.pkg` payload.

**Tests required**: Broker tests using `net.Pipe`-mocked UDS; happy path + timeout + concurrent requests; risk table coverage.

**Estimated complexity**: L (new package + new binary + spawn-time settings injection + build-tooling update).

**Dependencies**: V1.1 (uses the new `EventSessionPermissionRequest` builder).

**Agent type**: general-purpose (Go).

**Critical risks**:
- UDS path collisions across concurrent bridge processes — namespace per PID.
- Hook binary must be on `$PATH` or the settings overlay must use absolute path. Use absolute path constructed at bridge startup from `os.Executable()`.
- `--settings` file leak on crash — best-effort cleanup, but also a startup sweep of `$TMPDIR/rafraf-bridge-settings-*.json` older than 1 h.
- macOS sandboxing of the hook subprocess — needs an entitlement for UDS connect to a path inside `$TMPDIR`; will be tested in Wave 2 device test.

---

### V1.3 — Bridge EventSink wiring + Runner integration

**Title**: Surface permission_request through the EventSink and out the WSS
**Files to touch**:
- `apps/rafraf-bridge/internal/claude/runner.go` — extend `EventSink` with `OnPermissionRequest(ev protocol.EventSessionPermissionRequest) error`.
- `apps/rafraf-bridge/internal/claude/runner.go::Run` — inject the broker into the runner; pass it through to the parser via a new `Parser.SetPermissionBroker(b *permission.Broker)` setter (or via constructor change).
- `apps/rafraf-bridge/internal/claude/parser.go` — no actual parser change today (parser doesn't see hook-driven decisions); the EventSink call originates inside the broker when it receives a UDS request. The broker calls `sink.OnPermissionRequest(...)`, which the runner exposes via a closure that wraps the sink.
- `apps/rafraf-bridge/cmd/bridge/main.go::wsEventSink` — add `OnPermissionRequest(ev) → s.emit(protocol.NewEventSessionPermissionRequest(s.target(ev.SessionID), s.correlationID, ev))`.
- `apps/rafraf-bridge/cmd/bridge/main.go::dispatchCommand` — add cases for `command.claude.permission.allow|deny` that look up the (now process-wide) broker and call `broker.Resolve(...)`.

**Tests required**: Integration test in `apps/rafraf-bridge/integration_test.go` that fakes the claude subprocess (using existing `cat testdata/*.jsonl` pattern) plus a synthetic UDS hook simulator that fires `RequestDecision` and asserts the WSS egress sees the envelope; second test fires the inbound `command.claude.permission.allow` and asserts the broker resolves with `Allow`.

**Estimated complexity**: M.

**Dependencies**: V1.1, V1.2.

**Agent type**: general-purpose (Go).

**Critical risks**:
- Broker lifecycle vs. session lifecycle: a single broker survives multiple sessions but each request_id must be unique. Use UUIDv7 for time-ordering.
- correlation_id discipline: the bridge must echo the originating `command.claude.run`'s correlation_id on the `permission_request` envelope. Store it on the per-run `wsEventSink` (already there as `s.correlationID`) and have the broker invoke a closure that injects it.

---

### V1.4 — Backend orchestrator: handle permission_request + dispatch decision RPC

**Title**: Wire `event.session.permission_request` through the runner into ApprovalService
**Files to touch**:
- `apps/backend/app/orchestrator/claude_code_runner.py` — add `PermissionRequestCallback` type alias; new optional `on_permission_request` parameter on `run()`; new branch in `_dispatch_event_inner` for `event.session.permission_request` that:
  1. Builds `ApprovalRequestCreate` from the envelope.
  2. Calls `approval_service.create_approval(...)`.
  3. Calls `callbacks.on_permission_request(...)` (delegates iOS push + decision-awaiting to the websocket layer; runner passes `request_id`, `bridge_host_id`, `rpc_id` so the awaiter can dispatch the bridge envelope).
- `apps/backend/app/services/approval_service.py` — extend `ApprovalRequestCreate` schema with optional `request_id`, `bridge_host_id`, `rpc_id` so the post-decision dispatch has the routing info; persist them on the record.
- `apps/backend/app/api/routes/websocket.py::_process_with_orchestrator` — implement `_on_permission_request` callback that:
  1. Pushes the `MessageType.QUESTION` envelope to the iOS connection (via `manager.send_json`).
  2. Spawns `asyncio.create_task(_await_and_dispatch(record, bridge_host_id, rpc_id))`.
- New helper `_await_and_dispatch(record, bridge_host_id, rpc_id)` in `websocket.py` (or a new `permission_dispatcher.py` service):
  1. `result = await approval_service.wait_for_decision(record.id)`.
  2. Build envelope: `command.claude.permission.allow` if `result.approved` else `command.claude.permission.deny`. Set `correlation_id = rpc_id` (so the bridge's run-side handler can find the broker; though the broker itself routes by `request_id`, not by correlation_id).
  3. `await bridge_registry.send_to_bridge(bridge_host_id, envelope)`. On `False`, log `permission_dispatch_failed` and rely on the bridge-side timeout to deny.
  4. Call `audit_service.log_tool_call(...)` with the decision (closes runbook §11 gap #4 from T3.2-followup).
- `apps/backend/app/core/metrics.py` — add three counters:
  - `permission_request_emitted_total{bridge_id, tool_name, risk}`.
  - `permission_request_decided_total{bridge_id, decision}`.
  - `permission_request_timeout_total{bridge_id, tool_name}`.

**Tests required**: Extend `apps/backend/tests/integration/test_permission_flow.py` with a new TestClass that:
- Feeds a synthetic `event.session.permission_request` into the runner via a stubbed `bridge_registry.stream_events`, asserts `create_approval` is called with the right fields.
- Submits a decision via `submit_decision` and asserts `bridge_registry.send_to_bridge` was called with `command.claude.permission.allow` and the right `request_id`.
- Lets the timeout fire and asserts `command.claude.permission.deny` is sent automatically.

**Estimated complexity**: M.

**Dependencies**: V1.1 (envelope types must exist on the wire) — but Python side decodes JSON dicts so even without V1.1 published, this can develop in parallel against test fixtures. Sequencing: prefer V1.1 done first to avoid contract drift.

**Agent type**: general-purpose (Python/FastAPI).

**Critical risks**:
- Subagent permission requests carry `parent_task_id` — backend must associate the question with the lead session_id, not the subagent's task_id, so the iOS connection lookup hits the right user. This is straightforward because `event.session.permission_request.session_id` == lead session.
- Concurrent permission_requests for one user: the iOS app must be able to render multiple sheets stacked. RFApprovalSheet currently presents `.sheet(item: $request)` which is single-instance. We either (a) extend the coordinator to present a queue, or (b) constrain the bridge to serialise (not possible — claude parallelises subagents). **Recommendation**: stack queue — coordinator holds `[ApprovalSheetRequest]` and presents the head; on decision, dequeue and present next. This is part of V1.5 work.
- Reconnect during pending: if iOS reconnects mid-decision, the permission_request envelope is gone (it was pushed once). Solution: add a "snapshot replay" hook — on iOS reconnect, the WS endpoint queries `approval_service.get_session_pending(...)` and re-sends each pending question. (Already noted in runbook §9.2 as a follow-up; we ship a minimal version here.)

---

### V1.5 — iOS: register `question` MessageType + ApprovalCoordinator + sheet presentation

**Title**: Land the inbound `question` envelope and present RFApprovalSheet live
**Files to touch**:
- `apps/ios/RafRaf/Core/Networking/WebSocketMessage.swift` — add `case question = "question"` to `WebSocketMessageType`; add `case question(ApprovalQuestionDTO)` to `WebSocketContent` enum; add decode branch in `WebSocketBaseMessage.init(from:)` for the `question` type.
- `apps/ios/RafRaf/Core/Networking/WebSocketMessageRouter.swift` — route `case .question(let dto)` to `ApprovalCoordinator.shared.enqueue(dto)`.
- `apps/ios/RafRaf/Features/Approval/Presentation/Coordinators/ApprovalCoordinator.swift` (new) — `@Observable @MainActor final class ApprovalCoordinator`. Owns `var queue: [ApprovalSheetRequest] = []` and `var activeRequest: ApprovalSheetRequest? = nil`. `enqueue(dto:)` decodes via `ApprovalMapper`, appends, calls `presentNext()`.
- `apps/ios/RafRaf/Features/Approval/Data/Mappers/ApprovalMapper.swift` — add `toSheetRequest(question:) -> ApprovalSheetRequest` mapping ApprovalCategory → ApprovalDecisionPolicy.
- `apps/ios/RafRaf/App/ContentView.swift` (or `HomeView.swift`) — attach `.sheet(item: $coordinator.activeRequest) { req in RFApprovalSheet(request: req) { decision in coordinator.handleDecision(decision) } }`.
- `apps/ios/RafRaf/Features/Approval/Presentation/Coordinators/ApprovalCoordinator.swift::handleDecision` — call `submitDecisionUseCase.execute(approvalId: req.id, decision: decision == .deny ? .rejected : .approved, note: nil)`; pop queue; `presentNext()`.
- `apps/ios/RafRaf/Core/DI/AppContainer.swift` — register the coordinator as a `Container.shared` singleton.
- `apps/ios/RafRaf/Resources/Localizable.xcstrings` — no new strings needed; existing `approval.sheet.*` keys cover it.
- iOS tests: unit test the coordinator queue logic; UI test the sheet stacking under simulated parallel decisions.

**Estimated complexity**: M.

**Dependencies**: V1.4 (so the backend can actually emit the `question` envelope from a real bridge event).

**Agent type**: general-purpose (Swift / iOS).

**Critical risks**:
- The legacy `RFApprovalCard` + `ApprovalCardViewModel` remain in tree and may be wired to the same coordinator. Document that for V1 we ship `RFApprovalSheet` as the canonical surface; `RFApprovalCard` is preview-only.
- Allow-once vs Allow-session: `RFApprovalSheet` emits 3 choices (allowOnce / allowSession / deny). The wire only knows "approved" or "rejected". For V1, map both allow* to "approved"; surface session-allow as a future-Faz4 enhancement that piggy-backs on `note: "allow_session"` for backend deduplication. Document explicitly.

---

### V1.6 — Shared contracts + docs + observability

**Title**: Update API contracts, runbook, dashboards, audit emit
**Files to touch**:
- `shared/api-contracts/ws/approval-messages.json` — leave the existing `question` and `approval_response` schemas; add a new section documenting the bridge-leg `event.session.permission_request` envelope and the `command.claude.permission.allow|deny` envelopes (in the bridge-side contract, conventionally under a new file `shared/api-contracts/ws/bridge-permission-messages.json`).
- `docs/runbooks/permission-flow.md` — flip §11 Gap #1, #2, #4 from "deferred" to "shipped"; add a new §13 "End-to-end timeline" with the latency table from §2.2.4 above; remove the `xfail` marker in `test_audit_log_records_each_decision`.
- `infra/grafana/dashboards/` (if present) — add the three new permission counters to the bridge dashboard.
- `apps/backend/tests/integration/test_permission_flow.py` — un-xfail the audit test.

**Estimated complexity**: S.

**Dependencies**: V1.4, V1.5.

**Agent type**: general-purpose (docs + light test/dashboard edits).

**Critical risks**: minimal; docs-only.

---

### V1.7 — End-to-end smoke test (manual + scripted)

**Title**: Run the whole loop on a laptop bridge; verify timing + UX
**Files to touch**:
- `apps/backend/tests/integration/test_permission_flow_e2e.py` (new) — uses `httpx` to drive an actual iOS-shape WS client + a fake bridge that emits `event.session.permission_request` envelopes, asserts the round-trip completes within budget.
- `docs/runbooks/permission-flow.md` §14 "Manual smoke test" — step-by-step recipe for a developer to verify the flow with a real claude subprocess on their Mac.

**Estimated complexity**: S–M (the e2e test fixture is non-trivial but no new code).

**Dependencies**: V1.1 through V1.6.

**Agent type**: general-purpose (Python integration tester).

**Critical risks**: This is the gate to declaring V1 ready. If e2e fails, fix loop.

---

## 4. Risk register

### 4.1 Bridge process management gotchas

- **Hook subprocess inheritance**: The `claude -p` subprocess inherits the bridge's environment. The hook must NOT recursively launch a sub-bridge or read the same UDS socket that's already serving the parent. Use a unique env var `$RAFRAF_BRIDGE_PERM_SOCK` set by the bridge before spawning claude; the hook reads only this var.
- **stdin to claude**: the runner today does not write to claude's stdin (`runner.go` does not request `cmd.StdinPipe`). The hook approach avoids needing this — decisions flow via UDS, not stdin. Good.
- **Settings file race**: if two simultaneous `claude -p` runs share `~/.claude/settings.json`, hook installation could clash. Mitigation: per-request `--settings <file>` via the explicit CLI flag (verify in Wave 2 it actually overrides — claude CLI does support a per-invocation settings overlay via `--settings`; if not, switch to `~/.claude/settings.local.json` overlay merged at runtime).
- **launchd plist hardening (T3.6)**: the bridge's launchd plist must allow connecting to the UDS path inside `$TMPDIR`. Check sandbox profile.
- **PKG/notarization**: the new hook binary must be code-signed and notarised. Add to packaging/pkg payload.

### 4.2 Race conditions

- **Multiple permission_requests in flight**: handled by `request_id` keying on both broker and `ApprovalService` (already keys by UUID).
- **Decision arrives after timeout**: broker checks if waiter still exists before writing; backend `submit_decision` returns `False` if no waiter; safe.
- **Bridge disconnect during decision wait**: broker's `RequestDecision` blocks until ctx done; on bridge process restart, claude's hook subprocess is killed too (parent died), unblocking it (read from UDS returns EOF). The CLI should treat this as a denial (need to verify in Wave 2).
- **Backend restart during decision wait**: the asyncio Future in `ApprovalService` is lost; the bridge-side broker still waits, eventually times out and denies. Acceptable degradation.

### 4.3 Timeout cascades

| Layer | Default | Reason |
|---|---|---|
| iOS RFApprovalSheet countdown | 30 s | UX (Spike #5 baseline) |
| Backend `ApprovalService` per-category | 180 s (WRITE_REMOTE) / 300 s (others) | accommodates push-notification-then-app-open lag |
| Bridge UDS broker | `permission_request.timeout_ms` from envelope, default 30 s | mirrors iOS |
| Claude CLI hook timeout | 60 s (CLI default) | upper bound — must exceed bridge broker timeout |

**Inconsistency**: backend defaults are much higher than iOS RFApprovalSheet's 30 s. For V1, **iOS wins** — the user sees a 30 s timer; if they don't decide, iOS auto-denies and submits `decision: rejected`. Backend's 180 s window is then irrelevant because submit_decision lands first. Backend timeout is the safety net for app-killed-mid-question case. **No code change needed** but document explicitly.

The bridge `permission_request.timeout_ms` should equal iOS countdown so the bridge's own broker timeout aligns. **Recommend**: bridge sets `timeout_ms = 30_000` in the envelope; backend forwards it as `timeout_seconds` in the QUESTION payload; iOS RFApprovalSheet uses `request.timeoutSeconds` directly (already does).

### 4.4 Backwards compatibility

- **Old bridge + new backend**: the new event_type the backend handles is additive; an old bridge simply never emits `event.session.permission_request`. The new RPC types `command.claude.permission.allow|deny` will be silently ignored by old bridges (their `dispatchCommand` already has a default branch logging "ignoring envelope"). **Safe**.
- **New bridge + old backend**: the new bridge emits `event.session.permission_request`; the old backend's `_dispatch_event_inner` falls through the unknown-event branch (`logger.adebug("claude_rpc_unknown_event")`) and continues. The bridge's broker times out and denies. **Safe degradation**.
- **Rolling deploy**: backend goes first, bridges second. Backend handles both old-style (terminal denials only) and new-style (real-time requests). Same CI artefact for the bridge `.pkg` is shipped manually anyway (single Mac), so coordination is trivial.

### 4.5 Privacy / security

- The `permission_request.tool_input` payload may carry sensitive content (e.g. `Bash` command with secrets, file path with PII). The existing `input_preview` truncation to 240 bytes is a partial mitigation; backend must NOT log `tool_input` at info level. Add explicit `await logger.adebug` (not `ainfo`) in the new branch and document a redaction layer.
- The hook binary's UDS handshake should include a magic header so unrelated processes connecting to the socket get rejected.

---

## 5. Acceptance criteria

### 5.1 E2E test scenario

1. Developer starts a session through iOS chat: "Lütfen `tmp/build.log` dosyasını sil."
2. Backend forwards via `command.claude.run` (permission_mode=acceptEdits) to bridge.
3. Bridge spawns `claude -p ... --settings <generated-overlay>`. Overlay registers PreToolUse hook.
4. Claude decides to call `Bash` with `rm -rf tmp/build.log`. PreToolUse hook fires.
5. Hook sends `{tool_name: "Bash", tool_input: {...}, session_id: "..."}` to bridge UDS.
6. Bridge `permission.Broker.RequestDecision` registers waiter, classifies risk=high, builds `EventSessionPermissionRequest` with `request_id=<uuid>, timeout_ms=30000`, calls `OnPermissionRequest`.
7. wsEventSink emits `event.session.permission_request` envelope (correlation_id = run rpc_id).
8. Backend `_dispatch_event_inner` branch: `create_approval(category=DESTRUCTIVE, request_id=...)`, sends `MessageType.QUESTION` to iOS, spawns awaiter task.
9. iOS `WebSocketMessageRouter` decodes the question, `ApprovalCoordinator.enqueue` activates `RFApprovalSheet` with risk=high.
10. User taps "Reddet". iOS sends `approval_response{approval_id, decision: rejected}`.
11. Backend `_handle_approval_response` → `approval_service.submit_decision`. Awaiter task wakes up, builds `command.claude.permission.deny`, calls `send_to_bridge`.
12. Bridge `dispatchCommand` route → `broker.Resolve(request_id, Deny)`.
13. Hook unblocks, prints `{"decision": "block", "reason": "user denied"}`, exits.
14. Claude receives the denial, generates a refusal message: "Tool çağrısı reddedildi." → emits `assistant` event → eventually `result` event.
15. iOS sees normal stream end with the refusal text; the `result.permission_denials` array on the terminal envelope contains the request.
16. Audit log row for the rejected tool call exists with `approval_required=True`, `output_result={"decision": "rejected"}`.

**Pass criteria**:
- All WSS envelopes well-formed against schemas.
- Total wall-clock from step 4 → step 14 < 35 s when user taps deny within 5 s.
- `permission_request_emitted_total` counter incremented once.
- `permission_request_decided_total{decision="rejected"}` counter incremented once.
- No `permission_request_timeout_total` increment.
- Audit log emit happens (V1.4 closes the T3.2 xfail test).

### 5.2 Metric additions (Prometheus)

In `apps/backend/app/core/metrics.py`:
- `permission_request_emitted_total{bridge_id, tool_name, risk}` — counter, incremented on backend receipt.
- `permission_request_decided_total{bridge_id, tool_name, decision}` — counter (decision in {approved, rejected, expired, dispatch_failed}).
- `permission_request_round_trip_seconds{bridge_id}` — histogram, observed from envelope receipt to decision dispatch.

In `apps/rafraf-bridge/internal/telemetry/metrics.go` mirror three counters:
- `bridge_permission_requests_total`.
- `bridge_permission_decisions_total{decision}`.
- `bridge_permission_timeouts_total`.

### 5.3 Audit log expansion

`AuditService.log_tool_call(...)` is invoked at the `submit_decision` follow-through site (V1.4 helper) with:
- `tool_name = record.tool_name`
- `action = record.action`
- `success = result.approved`
- `user_id = <session owner UUID>`
- `input_params = record.params`
- `output_result = {"decision": result.decision, "request_id": record.id}`
- `approval_required = True`

Closes runbook §11 gap #4. The `xfail` marker on `test_audit_log_records_each_decision` is removed and the test passes naturally.

---

## 6. Open questions for user

1. **Ship A and B together vs. ship A first with a "best-effort deny" fallback?**
   Recommendation: ship together. Without B, the user can see the request but the bridge can't act on it — claude already moved past the tool_use. Half-shipping creates false confidence.

2. **PreToolUse hook strategy vs. `--permission-prompt-tool` MCP strategy?**
   Recommendation: PreToolUse hook (Strategy B). Simpler, no MCP server lifecycle. If Wave 2 device tests reveal hook reliability issues, fall back to `--permission-prompt-tool` in V1.5 with the same broker contract.

3. **Allow-once vs. Allow-session in iOS RFApprovalSheet → wire?**
   For V1, both map to "approved" with `note: "allow_session"` carried through. Backend ignores the note for V1 (treats as allow-once). Faz4 hook to extend `BridgeRegistryService` with a per-(session_id, tool_name) allowlist that short-circuits future requests.

4. **Risk classification authority — bridge or backend?**
   Recommendation: bridge. The bridge has direct access to `cwd`, can compare paths, and knows the whitelist. Backend only consumes the pre-classified `risk` string. This isolates classification logic in one place.

5. **Concurrent sheet UX**: stack-and-show-one vs. all-at-once?
   Recommendation: stack-and-show-one (queue). One full-screen sheet at a time; subsequent requests queue behind. Spike #5 didn't measure parallel approval UX; safer to over-constrain than to overwhelm.

6. **Bridge inbound channel capacity**: 64 sufficient, or larger?
   Recommendation: 64. Per-bridge inbound traffic is sparse (rate limited by user decisions). If overflow ever happens, log and drop with a metric; the CLI hook will time out and deny, which is the right failure mode.

7. **Hook binary distribution**: separate `.pkg` install path or embedded inside the bridge `.pkg`?
   Recommendation: embedded. The bridge installer drops both `rafraf-bridge` and `rafraf-perm-hook` into `/usr/local/bin/`. Bridge resolves the hook absolute path via `os.Executable()` + sibling lookup at startup so it works from any install layout.

8. **Should we also wire the `command.claude.abort` RPC (currently scaffolded in `dispatchCommand` but never callable)?**
   Stretch goal in the same Faz3 wave — once V1.1 lands, the inbound channel exists, and `dispatchCommand` already routes the type. Wiring an iOS "Cancel session" button to call it is ~1 day of work. **Out of scope for V1 blockers** but a strong follow-up.

---

### Critical Files for Implementation

- /Users/atakan/Documents/GitHub/atknatk/rafraf/apps/rafraf-bridge/internal/claude/runner.go
- /Users/atakan/Documents/GitHub/atknatk/rafraf/apps/rafraf-bridge/internal/protocol/messages.go
- /Users/atakan/Documents/GitHub/atknatk/rafraf/apps/rafraf-bridge/cmd/bridge/main.go
- /Users/atakan/Documents/GitHub/atknatk/rafraf/apps/backend/app/orchestrator/claude_code_runner.py
- /Users/atakan/Documents/GitHub/atknatk/rafraf/apps/ios/RafRaf/Core/Networking/WebSocketMessage.swift
