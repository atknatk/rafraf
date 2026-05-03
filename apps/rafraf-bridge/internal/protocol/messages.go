// Package protocol — message catalogue.
//
// This file defines every typed payload that flows through Envelope.Payload
// per docs/11_Bridge_Spec.md §3.3. Two directional groups exist:
//
//   - Inbound (backend → bridge): CommandClaude*
//   - Outbound (bridge → backend): EventSession*, EventStorage*, EventUsage*,
//     EventBridge*
//
// JSON tags follow the snake_case Pydantic convention used by the Python
// backend so payloads serialize/deserialize symmetrically.
package protocol

import "encoding/json"

// ---------------------------------------------------------------------------
// Type tag constants — every Envelope.Type value the bridge speaks or hears.
// ---------------------------------------------------------------------------

const (
	// Inbound (backend → bridge).
	TypeCommandClaudeRun             = "command.claude.run"
	TypeCommandClaudeAbort           = "command.claude.abort"
	TypeCommandClaudePermissionAllow = "command.claude.permission.allow"
	TypeCommandClaudePermissionDeny  = "command.claude.permission.deny"
	// V1.x Claude Subprocess Supervisor — inbound retry RPC.
	// Originator: iOS (Retry button tap). Consumers: Backend → bridge runner.
	// Bridge handler aborts any zombie supervised instance keyed by
	// session_id and re-issues a fresh Run() with the cached prompt.
	TypeCommandClaudeProcessRetry = "command.claude.process.retry"

	// Session events (bridge → backend).
	TypeEventSessionInit              = "event.session.init"
	TypeEventSessionAssistant         = "event.session.assistant"
	TypeEventSessionUser              = "event.session.user"
	TypeEventSessionStream            = "event.session.stream"
	TypeEventSessionTaskStarted       = "event.session.task_started"
	TypeEventSessionTaskProgress      = "event.session.task_progress"
	TypeEventSessionTaskNotification  = "event.session.task_notification"
	TypeEventSessionRateLimit         = "event.session.rate_limit"
	TypeEventSessionResult            = "event.session.result"
	TypeEventSessionHookStarted       = "event.session.hook_started"
	TypeEventSessionHookResponse      = "event.session.hook_response"
	TypeEventSessionPermissionRequest = "event.session.permission_request"

	// Storage events (bridge → backend).
	TypeEventStorageAITitle        = "event.storage.ai_title"
	TypeEventStoragePRLink         = "event.storage.pr_link"
	TypeEventStorageHookAttachment = "event.storage.hook_attachment"

	// Statusline events (bridge → backend).
	TypeEventUsageReport = "event.usage.report"

	// Bridge meta events (bridge → backend).
	TypeEventBridgeAlive       = "event.bridge.alive"
	TypeEventBridgeAuthExpired = "event.bridge.auth_expired"

	// V1.x Claude Subprocess Supervisor — outbound process lifecycle events.
	//
	// All six envelopes are bridge-originated, backend-relayed,
	// iOS-consumed. Outer envelope target is "session:<sessionID>" so
	// the backend dispatcher routes via the existing per-session
	// subscriber map; correlation_id mirrors the originating
	// command.claude.run rpc id.
	TypeEventClaudeProcessSpawned     = "event.claude.process.spawned"
	TypeEventClaudeProcessHealthcheck = "event.claude.process.healthcheck"
	TypeEventClaudeProcessStalled     = "event.claude.process.stalled"
	TypeEventClaudeProcessCrashed     = "event.claude.process.crashed"
	TypeEventClaudeProcessRecovered   = "event.claude.process.recovered"
	TypeEventClaudeProcessDiagnosed   = "event.claude.process.diagnosed"
)

// ---------------------------------------------------------------------------
// Inbound: backend → bridge.
// ---------------------------------------------------------------------------

// CommandClaudeRun launches a `claude -p` subprocess. SessionID, when nil,
// requests a fresh session. PermissionMode/AgentTeams/ProjectDir override
// values from config.toml when set.
type CommandClaudeRun struct {
	Prompt         string  `json:"prompt"`
	SessionID      *string `json:"session_id,omitempty"`
	PermissionMode string  `json:"permission_mode,omitempty"`
	AgentTeams     *bool   `json:"agent_teams,omitempty"`
	ProjectDir     *string `json:"project_dir,omitempty"`
	UserID         string  `json:"user_id"`
}

// CommandClaudeAbort signals the bridge to terminate an in-flight session.
type CommandClaudeAbort struct {
	SessionID string `json:"session_id"`
}

// CommandClaudeProcessRetry is the inbound payload for the V1.x
// Claude Subprocess Supervisor manual-retry RPC. iOS emits this when
// the user taps the Retry button on the Stalled banner / Diagnosed
// banner / Crashed push notification. Backend forwards verbatim. The
// bridge handler aborts any zombie supervised instance keyed by
// SessionID and re-issues a fresh Run() with the cached prompt
// captured at Register time.
type CommandClaudeProcessRetry struct {
	SessionID string `json:"session_id"`
	UserID    string `json:"user_id"`
}

// CommandClaudePermissionDecision is the inbound RPC payload for the
// command.claude.permission.allow and command.claude.permission.deny
// envelopes. It carries the user's decision back to the bridge so the
// permission Broker can resolve the matching in-flight PreToolUse hook.
//
// RequestID identifies the originating event.session.permission_request
// envelope (the bridge-generated UUID). SessionID echoes the lead claude
// session for observability + audit. Decision is the canonical "allow" or
// "deny" string (matching the Strategy B hook contract). Reason is a
// free-form audit string surfaced into structured logs. UpdatedInput is
// reserved for the MCP-style "permission tool returns a modified
// tool_input" branch and is ignored by V1; downstream V2/V3 work may wire
// it through the broker into the hook reply.
type CommandClaudePermissionDecision struct {
	SessionID    string          `json:"session_id"`
	RequestID    string          `json:"request_id"`
	Decision     string          `json:"decision"`
	Reason       string          `json:"reason,omitempty"`
	UpdatedInput json.RawMessage `json:"updated_input,omitempty"`
}

// ---------------------------------------------------------------------------
// Outbound: bridge → backend — Session events.
// ---------------------------------------------------------------------------

// EventSessionInit captures the system/init event emitted at the start of
// every claude stream-json run.
type EventSessionInit struct {
	SessionID      string   `json:"session_id"`
	CWD            string   `json:"cwd"`
	Model          string   `json:"model"`
	Tools          []string `json:"tools"`
	PermissionMode string   `json:"permission_mode"`
	APIKeySource   string   `json:"api_key_source"`
	Version        string   `json:"version"`
}

// EventSessionAssistant carries an assistant message verbatim. The payload is
// preserved as json.RawMessage so the backend can decode it into Pydantic
// without an intermediate Go schema bound.
type EventSessionAssistant struct {
	SessionID string          `json:"session_id"`
	Message   json.RawMessage `json:"message"`
}

// EventSessionUser carries a user-role message (typically tool_result frames
// echoed by the model).
type EventSessionUser struct {
	SessionID string          `json:"session_id"`
	Message   json.RawMessage `json:"message"`
}

// EventSessionStream is a partial-message delta — emitted when claude is
// invoked with `--include-partial-messages`.
type EventSessionStream struct {
	SessionID string          `json:"session_id"`
	Delta     json.RawMessage `json:"delta"`
}

// EventSessionTaskStarted fires when claude dispatches a sub-agent task. The
// PromptPreview is a truncated copy of the orchestrator prompt suitable for
// surfacing in the UI without leaking the full instruction.
type EventSessionTaskStarted struct {
	SessionID     string `json:"session_id"`
	TaskID        string `json:"task_id"`
	Description   string `json:"description"`
	SubagentType  string `json:"subagent_type"`
	Isolation     string `json:"isolation"`
	PromptPreview string `json:"prompt_preview"`
}

// EventSessionTaskProgress carries an intermediate status update for a
// running sub-agent task. The shape mirrors the Python
// `build_claude_stream_progress_message` content payload.
type EventSessionTaskProgress struct {
	SessionID   string            `json:"session_id"`
	TaskID      string            `json:"task_id"`
	Phase       string            `json:"phase"`
	PhaseLabel  string            `json:"phase_label"`
	CurrentTool *string           `json:"current_tool,omitempty"`
	Percentage  int               `json:"percentage"`
	Steps       []json.RawMessage `json:"steps"`
}

// EventSessionTaskNotification fires when a sub-agent task terminates.
type EventSessionTaskNotification struct {
	SessionID   string `json:"session_id"`
	TaskID      string `json:"task_id"`
	Status      string `json:"status"`
	Summary     string `json:"summary"`
	TotalTokens int    `json:"total_tokens"`
	ToolUses    int    `json:"tool_uses"`
	DurationMs  int    `json:"duration_ms"`
}

// EventSessionRateLimit reports rate-limit telemetry from the claude CLI.
type EventSessionRateLimit struct {
	SessionID      string `json:"session_id"`
	Status         string `json:"status"`
	RateLimitType  string `json:"rate_limit_type"`
	ResetsAt       int64  `json:"resets_at"`
	OverageStatus  string `json:"overage_status"`
	IsUsingOverage bool   `json:"is_using_overage"`
}

// ModelUsage breaks down per-model token consumption inside EventSessionResult.
type ModelUsage struct {
	InputTokens         int `json:"input_tokens"`
	OutputTokens        int `json:"output_tokens"`
	CacheReadTokens     int `json:"cache_read_input_tokens"`
	CacheCreationTokens int `json:"cache_creation_input_tokens"`
}

// EventSessionResult is the terminal event for a session — emitted exactly
// once when the claude subprocess exits cleanly.
type EventSessionResult struct {
	SessionID         string                `json:"session_id"`
	DurationMs        int                   `json:"duration_ms"`
	NumTurns          int                   `json:"num_turns"`
	Result            string                `json:"result"`
	StopReason        string                `json:"stop_reason"`
	TotalCostUSD      float64               `json:"total_cost_usd"`
	ModelUsage        map[string]ModelUsage `json:"model_usage"`
	PermissionDenials []json.RawMessage     `json:"permission_denials"`
	TerminalReason    string                `json:"terminal_reason"`
}

// EventSessionHookStarted fires when a Claude lifecycle hook (PreToolUse,
// PostToolUse, etc.) begins executing.
type EventSessionHookStarted struct {
	SessionID string `json:"session_id"`
	HookName  string `json:"hook_name"`
	Phase     string `json:"phase"`
}

// EventSessionHookResponse fires when a hook completes, carrying its raw
// result payload for backend interpretation.
type EventSessionHookResponse struct {
	SessionID string          `json:"session_id"`
	HookName  string          `json:"hook_name"`
	Result    json.RawMessage `json:"result"`
}

// EventSessionPermissionRequest fires from the bridge's PreToolUse hook
// path (Strategy B in docs/design/v1-permission-blockers.md §2.1.1) when
// a tool call needs explicit user approval. The request_id is a
// bridge-generated UUID that serves as the decision-correlation token —
// the iOS approval UI echoes it back via approval_response, and the
// backend rebroadcasts it as the request_id field on the inbound
// command.claude.permission.allow|deny RPC. The envelope's outer
// correlation_id always carries the originating command.claude.run rpc
// id so the backend orchestrator can route it into the correct
// per-session subscriber queue.
//
// ToolInput preserves the raw claude PreToolUse payload byte-for-byte so
// the backend can decode it into Pydantic without an intermediate Go
// schema bound; InputPreview is a 240-byte truncated text suitable for
// display on iOS without leaking large file diffs. Risk is "low",
// "medium", or "high" — classification authority lives in the bridge
// (it has direct access to cwd + path comparisons + the bash whitelist).
// TimeoutMs is the bridge-suggested ceiling (default 180000 as of
// V1.4-followup; previously 30000); iOS sets its countdown to this
// value and the bridge's broker times out at TimeoutMs + grace.
// Operators can override the bridge default via the
// `permission_timeout` TOML key (config.PermissionTimeout, validated
// to (0, 600s]). ParentTaskID is set when the PreToolUse hook fires
// from inside a sub-agent task so the backend can attribute the question
// to the lead session.
type EventSessionPermissionRequest struct {
	SessionID    string          `json:"session_id"`
	RequestID    string          `json:"request_id"`
	ToolName     string          `json:"tool_name"`
	ToolInput    json.RawMessage `json:"tool_input"`
	InputPreview string          `json:"input_preview"`
	Risk         string          `json:"risk"`
	Reason       string          `json:"reason,omitempty"`
	TimeoutMs    int             `json:"timeout_ms"`
	ParentTaskID string          `json:"parent_task_id,omitempty"`
}

// ---------------------------------------------------------------------------
// Outbound: V1.x Claude Subprocess Supervisor process-lifecycle events.
//
// All six structs serialise to snake_case keys to match the V1.x spec
// shared/feature-specs/V1x-claude-supervisor.md §4. Backend (Pydantic)
// + iOS (Codable) decode field-for-field.
// ---------------------------------------------------------------------------

// EventClaudeProcessSpawned fires once per supervised instance when
// cmd.Start() succeeds. Args excludes the prompt itself (PII guard —
// the orchestrator instruction never leaves the bridge through this
// channel). PID is the OS process id, StartedAt is ISO-8601 UTC.
type EventClaudeProcessSpawned struct {
	SessionID      string   `json:"session_id"`
	PID            int      `json:"pid"`
	StartedAt      string   `json:"started_at"`
	Model          string   `json:"model"`
	Args           []string `json:"args"`
	PermissionMode string   `json:"permission_mode"`
	ProjectDir     string   `json:"project_dir"`
}

// EventClaudeProcessHealthcheck is emitted on probe ticks, coalesced to
// at most one per same-state per session per healthcheck_coalesce
// window (default 30s) per spec §4.2 + Q6 default. Status is one of
// {starting, running, idle, stale, rate_limited, completed}.
// CurrentTokens is best-effort from the parser tally (zero when unknown).
// CPUPercent1s is computed from two getrusage samples per probe; falls
// back to 0 on platform errors.
type EventClaudeProcessHealthcheck struct {
	SessionID       string  `json:"session_id"`
	PID             int     `json:"pid"`
	Status          string  `json:"status"`
	LastStdoutAgeMs int64   `json:"last_stdout_age_ms"`
	CurrentTokens   int     `json:"current_tokens"`
	MemoryRSSKB     int64   `json:"memory_rss_kb"`
	CPUPercent1s    float64 `json:"cpu_percent_1s"`
	ObservedAt      string  `json:"observed_at"`
}

// EventClaudeProcessStalled is emitted exactly once per stale episode
// (re-entry into stale after a running blip restarts the counter and
// re-emits). StderrTail is capped at 8 KiB; StderrTailTruncated signals
// overflow. SelfHealPending is true when a diagnostic spawn is about
// to fire; false when rate-limit cache short-circuited.
type EventClaudeProcessStalled struct {
	SessionID           string `json:"session_id"`
	PID                 int    `json:"pid"`
	LastActivityAt      string `json:"last_activity_at"`
	StaleForMs          int64  `json:"stale_for_ms"`
	StderrTail          string `json:"stderr_tail"`
	StderrTailTruncated bool   `json:"stderr_tail_truncated"`
	SelfHealPending     bool   `json:"self_heal_pending"`
}

// EventClaudeProcessCrashed is emitted on cmd.Wait() non-zero exit OR
// when a diagnostic confirms the lead process is dead. Signal is the
// empty string when the exit was clean-but-nonzero (no signal). ExitCode
// is the OS-level exit status (-1 if unknown).
type EventClaudeProcessCrashed struct {
	SessionID  string `json:"session_id"`
	PID        int    `json:"pid"`
	ExitCode   int    `json:"exit_code"`
	Signal     string `json:"signal"`
	StderrTail string `json:"stderr_tail"`
	DurationMs int64  `json:"duration_ms"`
	CrashedAt  string `json:"crashed_at"`
}

// EventClaudeProcessRecovered fires on stale→running OR
// rate_limited→running OR after a manual retry. RecoveryReason ∈
// {diagnostic_recommended_wait, rate_limit_window_expired, manual_retry,
// stdout_resumed}. OldSessionID == NewSessionID for self-recovery and
// differs only on a manual retry that issued a fresh command.claude.run.
type EventClaudeProcessRecovered struct {
	OldSessionID   string `json:"old_session_id"`
	NewSessionID   string `json:"new_session_id"`
	RecoveryReason string `json:"recovery_reason"`
	RecoveredAt    string `json:"recovered_at"`
}

// EventClaudeProcessDiagnosed fires when the diagnostic claude
// completes. RecommendedAction ∈ {retry, wait, manual}. DiagnosisText
// capped at 4 KiB. DiagnosticTokensUsed informational, derived from
// the diagnostic claude's EventSessionResult; bridge enforces the
// ≤500 cost guard.
type EventClaudeProcessDiagnosed struct {
	SessionID            string `json:"session_id"`
	DiagnosisText        string `json:"diagnosis_text"`
	RecommendedAction    string `json:"recommended_action"`
	DiagnosticTokensUsed int    `json:"diagnostic_tokens_used"`
	DiagnosticDurationMs int64  `json:"diagnostic_duration_ms"`
	DiagnosedAt          string `json:"diagnosed_at"`
}

// ---------------------------------------------------------------------------
// Outbound: Storage events (~/.claude/projects/ watcher).
// ---------------------------------------------------------------------------

// EventStorageAITitle reports the AI-generated session title written to
// ~/.claude/projects/<project>/<session>.json.
type EventStorageAITitle struct {
	SessionID string `json:"session_id"`
	Title     string `json:"title"`
}

// EventStoragePRLink reports a pull-request link discovered in storage
// (typically created by a hook after `gh pr create`).
type EventStoragePRLink struct {
	SessionID    string `json:"session_id"`
	PRNumber     int    `json:"pr_number"`
	PRURL        string `json:"pr_url"`
	PRRepository string `json:"pr_repository"`
	Timestamp    string `json:"timestamp"`
}

// EventStorageHookAttachment carries an arbitrary hook-emitted attachment.
// AttachmentType is a free-form discriminator (e.g. "screenshot", "diff");
// Payload preserves the original JSON for backend decoding.
type EventStorageHookAttachment struct {
	SessionID      string          `json:"session_id"`
	AttachmentType string          `json:"attachment_type"`
	Payload        json.RawMessage `json:"payload"`
}

// ---------------------------------------------------------------------------
// Outbound: Statusline (~/.claude/usage.json).
// ---------------------------------------------------------------------------

// EventUsageReport summarises Claude Code usage windows for the statusline.
type EventUsageReport struct {
	FiveHourPct      int   `json:"five_hour_pct"`
	SevenDayPct      int   `json:"seven_day_pct"`
	FiveHourResetsAt int64 `json:"five_hour_resets_at"`
	SevenDayResetsAt int64 `json:"seven_day_resets_at"`
	ReportedAt       int64 `json:"reported_at"`
}

// ---------------------------------------------------------------------------
// Outbound: Bridge meta.
// ---------------------------------------------------------------------------

// EventBridgeAlive is a heartbeat-style health check announcing the bridge
// is still running. Emitted periodically (default every 60s).
type EventBridgeAlive struct {
	Connected     bool   `json:"connected"`
	UptimeSeconds int64  `json:"uptime_seconds"`
	BridgeVersion string `json:"bridge_version"`
	Hostname      string `json:"hostname"`
}

// EventBridgeAuthExpired is sent when the bridge detects that the local
// `claude` CLI has lost its authentication (logout or subscription expiry).
type EventBridgeAuthExpired struct {
	Reason string `json:"reason"`
}
