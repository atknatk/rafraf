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
	TypeCommandClaudeRun   = "command.claude.run"
	TypeCommandClaudeAbort = "command.claude.abort"

	// Session events (bridge → backend).
	TypeEventSessionInit             = "event.session.init"
	TypeEventSessionAssistant        = "event.session.assistant"
	TypeEventSessionUser             = "event.session.user"
	TypeEventSessionStream           = "event.session.stream"
	TypeEventSessionTaskStarted      = "event.session.task_started"
	TypeEventSessionTaskProgress     = "event.session.task_progress"
	TypeEventSessionTaskNotification = "event.session.task_notification"
	TypeEventSessionRateLimit        = "event.session.rate_limit"
	TypeEventSessionResult           = "event.session.result"
	TypeEventSessionHookStarted      = "event.session.hook_started"
	TypeEventSessionHookResponse     = "event.session.hook_response"

	// Storage events (bridge → backend).
	TypeEventStorageAITitle        = "event.storage.ai_title"
	TypeEventStoragePRLink         = "event.storage.pr_link"
	TypeEventStorageHookAttachment = "event.storage.hook_attachment"

	// Statusline events (bridge → backend).
	TypeEventUsageReport = "event.usage.report"

	// Bridge meta events (bridge → backend).
	TypeEventBridgeAlive       = "event.bridge.alive"
	TypeEventBridgeAuthExpired = "event.bridge.auth_expired"
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
