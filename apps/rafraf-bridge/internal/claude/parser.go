// Package claude — stream-json parser.
//
// The Parser reads NDJSON output from a `claude -p --output-format
// stream-json` subprocess line by line, decodes each line into the
// appropriate typed payload, mutates the companion StreamState for any
// longitudinal fields (subagents, rate-limit, cost), and dispatches the
// event to the Runner-supplied EventSink.
//
// Event catalogue (docs/11_Bridge_Spec.md §6 + docs/10_Production_Pivot_Spec.md §2.3):
//
//   - system/init             — session metadata
//   - system/task_started     — sub-agent spawned
//   - system/task_progress    — sub-agent intermediate update
//   - system/task_notification— sub-agent terminated
//   - system/hook_started     — Pre/PostToolUse hook lifecycle start
//   - system/hook_response    — Pre/PostToolUse hook lifecycle end
//   - system/status           — session status update (logged, no callback)
//   - assistant               — assistant turn (raw passthrough)
//   - user                    — user/tool_result turn (raw passthrough)
//   - stream_event            — partial-message delta (raw passthrough)
//   - rate_limit_event        — quota snapshot
//   - result                  — terminal session summary
//
// JSON-shape mismatches between the CLI (camelCase: rateLimitType,
// resetsAt, modelUsage) and the bridge protocol (snake_case) are absorbed
// here so the EventSink and downstream WebSocket envelopes only ever see
// the canonical RafRaf shape.
//
// Resilience: any per-line parse failure is logged at warn level and the
// scanner continues. A single bad line must never kill an in-flight
// session — a stuck subagent at the tail end of a 10-minute run can still
// surface its task_notification even if the assistant content frame
// before it was malformed.

package claude

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"time"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/trace"

	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/protocol"
	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/telemetry"
)

// Parser owns the NDJSON scanner and the StreamState that accumulates
// across the lifetime of a single `claude -p` invocation. Construct one
// per Runner.Run call; Parsers are not safe for reuse across runs.
type Parser struct {
	sink     EventSink
	logger   *slog.Logger
	state    *StreamState
	traceCtx context.Context
}

// NewParser constructs a Parser bound to the given sink. A nil logger is
// substituted with slog.Default() so call sites need not check.
//
// As of T0.5.6 the parser invokes EventSink callbacks on every recognised
// stream-json frame; passing a nil sink will panic on the first event.
func NewParser(sink EventSink, logger *slog.Logger) *Parser {
	if logger == nil {
		logger = slog.Default()
	}
	return &Parser{
		sink:     sink,
		logger:   logger,
		state:    NewStreamState(),
		traceCtx: context.Background(),
	}
}

// SetTraceContext attaches the parent OTel context that per-event spans
// should chain off. Called by the Runner so dispatch_event spans appear
// as children of the surrounding claude.parser.parse span. Defaults to
// context.Background when unset (no parent span — spans still emit but
// won't roll up under the parser parent).
func (p *Parser) SetTraceContext(ctx context.Context) {
	if ctx == nil {
		ctx = context.Background()
	}
	p.traceCtx = ctx
}

// State exposes the parser's accumulated StreamState. Useful for tests
// and for future per-run reporters that want the post-run snapshot of
// subagents, rate limit, and cumulative cost.
func (p *Parser) State() *StreamState { return p.state }

// Parse reads NDJSON lines from stdout until EOF or a scanner error. Each
// line is decoded and dispatched to the appropriate EventSink callback.
// Returns the underlying scanner error (typically nil on clean EOF) so the
// Runner can surface it as a parse error if non-nil.
func (p *Parser) Parse(stdout io.Reader) error {
	scanner := bufio.NewScanner(stdout)
	scanner.Buffer(make([]byte, stdoutInitialBufSize), stdoutMaxLineSize)
	for scanner.Scan() {
		telemetry.ClaudeLinesRead.Add(1)
		// scanner.Bytes() aliases the scanner's internal buffer; copy so
		// downstream handlers can retain references safely (e.g. into
		// json.RawMessage fields embedded in EventSession* payloads).
		line := append([]byte(nil), scanner.Bytes()...)
		if err := p.handleLine(line); err != nil {
			p.logger.Warn("claude parse error", "err", err, "line_len", len(line))
			// Continue — a single malformed line must not abort the stream.
		}
	}
	return scanner.Err()
}

// handleLine routes a single stream-json frame to its typed handler based
// on the top-level `type` discriminator (and `subtype` for system frames).
// Returns an error only when the line cannot be decoded as JSON; per-event
// payload mismatches are handled inside the dedicated handlers.
//
// Per-line work is wrapped in a “claude.parser.dispatch_event“ span so
// traces show one child per stream-json frame (and per-subagent
// transitions surface as span events emitted from the system/* handlers
// below).
func (p *Parser) handleLine(line []byte) error {
	var head struct {
		Type    string `json:"type"`
		Subtype string `json:"subtype,omitempty"`
	}
	if err := json.Unmarshal(line, &head); err != nil {
		return fmt.Errorf("decode head: %w", err)
	}

	tracer := otel.Tracer(claudeTracerName)
	eventType := head.Type
	if head.Subtype != "" {
		eventType = head.Type + "/" + head.Subtype
	}
	_, span := tracer.Start(p.traceCtx, "claude.parser.dispatch_event",
		trace.WithAttributes(attribute.String("claude.event_type", eventType)),
	)
	defer span.End()

	switch head.Type {
	case "system":
		return p.handleSystem(head.Subtype, line, span)
	case "assistant":
		return p.handleAssistant(line)
	case "user":
		return p.handleUser(line)
	case "stream_event":
		return p.handleStreamEvent(line)
	case "rate_limit_event":
		return p.handleRateLimit(line)
	case "result":
		return p.handleResult(line)
	default:
		// Unknown top-level type — log at debug level and ignore. Future
		// claude CLI versions may add new frames without breaking the
		// bridge.
		p.logger.Debug("claude unknown stream type", "type", head.Type)
		return nil
	}
}

// ---------------------------------------------------------------------------
// system/* dispatch.
// ---------------------------------------------------------------------------

// handleSystem dispatches on subtype. The catalogue is intentionally
// closed — unknown subtypes log at debug and return nil so the stream
// keeps moving.
//
// span is the active claude.parser.dispatch_event span; subagent
// lifecycle handlers attach span events to it so dashboards can surface
// transitions without inventing extra spans.
func (p *Parser) handleSystem(subtype string, line []byte, span trace.Span) error {
	switch subtype {
	case "init":
		return p.handleSystemInit(line)
	case "task_started":
		return p.handleSystemTaskStarted(line, span)
	case "task_progress":
		return p.handleSystemTaskProgress(line)
	case "task_notification":
		return p.handleSystemTaskNotification(line, span)
	case "hook_started":
		return p.handleSystemHookStarted(line)
	case "hook_response":
		return p.handleSystemHookResponse(line)
	case "status":
		// Session-level status updates are informational; no event sink
		// method exists for them yet (T0.5.6 scope cap). Logged at debug
		// for future observability work.
		p.logger.Debug("claude system status", "line_len", len(line))
		return nil
	default:
		p.logger.Debug("claude unknown system subtype", "subtype", subtype)
		return nil
	}
}

// handleSystemInit decodes the once-per-stream session metadata frame,
// records it on the StreamState, and forwards a typed
// EventSessionInit to the sink.
func (p *Parser) handleSystemInit(line []byte) error {
	var raw struct {
		SessionID      string   `json:"session_id"`
		CWD            string   `json:"cwd"`
		Model          string   `json:"model"`
		Tools          []string `json:"tools"`
		PermissionMode string   `json:"permissionMode"`
		APIKeySource   string   `json:"apiKeySource"`
		Version        string   `json:"version"`
	}
	if err := json.Unmarshal(line, &raw); err != nil {
		return fmt.Errorf("decode system/init: %w", err)
	}

	// Tool names in init.tools[] are the CLI's raw catalogue; canonicalise
	// each so the iOS client only ever sees the post-alias name (e.g.
	// "Task" → "Agent" per ADR-0005).
	canonicalTools := make([]string, len(raw.Tools))
	for i, t := range raw.Tools {
		canonicalTools[i] = CanonicalToolName(t)
	}

	p.state.SetSessionMeta(raw.SessionID, raw.Model, raw.PermissionMode, raw.APIKeySource)

	ev := protocol.EventSessionInit{
		SessionID:      raw.SessionID,
		CWD:            raw.CWD,
		Model:          raw.Model,
		Tools:          canonicalTools,
		PermissionMode: raw.PermissionMode,
		APIKeySource:   raw.APIKeySource,
		Version:        raw.Version,
	}
	return p.sink.OnInit(ev)
}

// handleSystemTaskStarted decodes a sub-agent spawn frame, registers the
// new SubagentState on the StreamState, and forwards a typed
// EventSessionTaskStarted to the sink.
//
// Field mapping note: the spike's run-1 fixture uses task_type/prompt
// (no description, no subagent_type). The protocol type accepts the
// richer Doc 11 §6 shape; missing fields fall through as their zero
// values which the iOS client tolerates.
//
// Emits a “subagent.spawned“ span event on the dispatch span so
// observability dashboards can correlate subagent lifecycles to the
// parent claude.parser.parse span.
func (p *Parser) handleSystemTaskStarted(line []byte, span trace.Span) error {
	var raw struct {
		SessionID    string `json:"session_id"`
		TaskID       string `json:"task_id"`
		Description  string `json:"description"`
		SubagentType string `json:"subagent_type"`
		TaskType     string `json:"task_type"`
		Isolation    string `json:"isolation"`
		Prompt       string `json:"prompt"`
	}
	if err := json.Unmarshal(line, &raw); err != nil {
		return fmt.Errorf("decode system/task_started: %w", err)
	}

	// SubagentType is a label (general-purpose, Explore, plugin:agent…),
	// not a tool name, so no aliasing applies. The Python reference does
	// not canonicalise it either. We do, however, fall back to TaskType
	// when SubagentType is empty so older CLI shapes stay legible.
	subagentType := raw.SubagentType
	if subagentType == "" {
		subagentType = raw.TaskType
	}

	sub := &SubagentState{
		TaskID:       raw.TaskID,
		Description:  raw.Description,
		SubagentType: subagentType,
		Isolation:    raw.Isolation,
		Prompt:       raw.Prompt,
		StartedAt:    time.Now(),
		Status:       "active",
	}
	p.state.RegisterSubagent(sub)

	span.AddEvent("subagent.spawned", trace.WithAttributes(
		attribute.String("subagent.session_id", raw.SessionID),
		attribute.String("subagent.task_id", raw.TaskID),
		attribute.String("subagent.type", subagentType),
	))

	ev := protocol.EventSessionTaskStarted{
		SessionID:     raw.SessionID,
		TaskID:        raw.TaskID,
		Description:   raw.Description,
		SubagentType:  subagentType,
		Isolation:     raw.Isolation,
		PromptPreview: truncatePrompt(raw.Prompt, promptPreviewMaxLen),
	}
	return p.sink.OnTaskStarted(ev)
}

// handleSystemTaskProgress decodes an intermediate sub-agent update and
// dispatches without mutating state — progress frames are advisory; the
// subagent's terminal state arrives via task_notification.
func (p *Parser) handleSystemTaskProgress(line []byte) error {
	var raw struct {
		SessionID   string `json:"session_id"`
		TaskID      string `json:"task_id"`
		Phase       string `json:"phase"`
		PhaseLabel  string `json:"phase_label"`
		LastTool    string `json:"last_tool_name"`
		CurrentTool string `json:"current_tool"`
		Percentage  int    `json:"percentage"`
		// Steps is left as raw so the iOS client can decode the richer
		// shape directly. The CLI does not always emit it.
		Steps []json.RawMessage `json:"steps"`
	}
	if err := json.Unmarshal(line, &raw); err != nil {
		return fmt.Errorf("decode system/task_progress: %w", err)
	}

	// Prefer current_tool (newer CLI) over last_tool_name (run-1 fixture);
	// canonicalise either before forwarding.
	currentTool := raw.CurrentTool
	if currentTool == "" {
		currentTool = raw.LastTool
	}
	var currentToolPtr *string
	if currentTool != "" {
		canon := CanonicalToolName(currentTool)
		currentToolPtr = &canon
	}

	steps := raw.Steps
	if steps == nil {
		steps = []json.RawMessage{}
	}

	ev := protocol.EventSessionTaskProgress{
		SessionID:   raw.SessionID,
		TaskID:      raw.TaskID,
		Phase:       raw.Phase,
		PhaseLabel:  raw.PhaseLabel,
		CurrentTool: currentToolPtr,
		Percentage:  raw.Percentage,
		Steps:       steps,
	}
	return p.sink.OnTaskProgress(ev)
}

// handleSystemTaskNotification decodes the sub-agent terminal frame,
// finalises the SubagentState on the StreamState, and forwards a typed
// EventSessionTaskNotification to the sink.
//
// Emits a “subagent.completed“ span event on the dispatch span so
// dashboards see the terminal status alongside the spawn event.
func (p *Parser) handleSystemTaskNotification(line []byte, span trace.Span) error {
	var raw struct {
		SessionID string `json:"session_id"`
		TaskID    string `json:"task_id"`
		Status    string `json:"status"`
		Summary   string `json:"summary"`
		Usage     struct {
			TotalTokens int `json:"total_tokens"`
			ToolUses    int `json:"tool_uses"`
			DurationMs  int `json:"duration_ms"`
			// Some CLI versions break tokens out further; capture if present.
			InputTokens  int `json:"input_tokens"`
			OutputTokens int `json:"output_tokens"`
			CacheRead    int `json:"cache_read_input_tokens"`
			CacheWrite   int `json:"cache_creation_input_tokens"`
		} `json:"usage"`
	}
	if err := json.Unmarshal(line, &raw); err != nil {
		return fmt.Errorf("decode system/task_notification: %w", err)
	}

	usage := &SubagentUsage{
		InputTokens:  raw.Usage.InputTokens,
		OutputTokens: raw.Usage.OutputTokens,
		CacheRead:    raw.Usage.CacheRead,
		CacheWrite:   raw.Usage.CacheWrite,
		TotalTokens:  raw.Usage.TotalTokens,
		ToolUses:     raw.Usage.ToolUses,
		DurationMs:   raw.Usage.DurationMs,
	}
	p.state.CompleteSubagent(raw.TaskID, raw.Status, usage)

	span.AddEvent("subagent.completed", trace.WithAttributes(
		attribute.String("subagent.session_id", raw.SessionID),
		attribute.String("subagent.task_id", raw.TaskID),
		attribute.String("subagent.status", raw.Status),
		attribute.Int("subagent.total_tokens", raw.Usage.TotalTokens),
		attribute.Int("subagent.duration_ms", raw.Usage.DurationMs),
	))

	ev := protocol.EventSessionTaskNotification{
		SessionID:   raw.SessionID,
		TaskID:      raw.TaskID,
		Status:      raw.Status,
		Summary:     raw.Summary,
		TotalTokens: raw.Usage.TotalTokens,
		ToolUses:    raw.Usage.ToolUses,
		DurationMs:  raw.Usage.DurationMs,
	}
	return p.sink.OnTaskNotification(ev)
}

// handleSystemHookStarted decodes a hook-lifecycle start frame and
// forwards it. Phase is the hook event (PreToolUse, PostToolUse, etc.);
// HookName is the registered handler identifier (e.g. "PreToolUse:Bash").
func (p *Parser) handleSystemHookStarted(line []byte) error {
	var raw struct {
		SessionID string `json:"session_id"`
		HookName  string `json:"hook_name"`
		HookEvent string `json:"hook_event"`
	}
	if err := json.Unmarshal(line, &raw); err != nil {
		return fmt.Errorf("decode system/hook_started: %w", err)
	}
	ev := protocol.EventSessionHookStarted{
		SessionID: raw.SessionID,
		HookName:  raw.HookName,
		Phase:     raw.HookEvent,
	}
	return p.sink.OnHookStarted(ev)
}

// handleSystemHookResponse decodes a hook-lifecycle end frame, packs the
// hook output into a json.RawMessage so the backend can decode against
// its own schema, and forwards it.
func (p *Parser) handleSystemHookResponse(line []byte) error {
	var raw struct {
		SessionID string          `json:"session_id"`
		HookName  string          `json:"hook_name"`
		Output    json.RawMessage `json:"output"`
		Outcome   string          `json:"outcome"`
		ExitCode  int             `json:"exit_code"`
		Stdout    string          `json:"stdout"`
		Stderr    string          `json:"stderr"`
	}
	if err := json.Unmarshal(line, &raw); err != nil {
		return fmt.Errorf("decode system/hook_response: %w", err)
	}

	// Build a normalised result envelope so the backend sees a stable
	// shape regardless of which fields the CLI populates. Output (when
	// present) wins; otherwise wrap stdout/stderr/exit_code.
	result := raw.Output
	if len(result) == 0 {
		envelope := map[string]any{
			"outcome":   raw.Outcome,
			"exit_code": raw.ExitCode,
			"stdout":    raw.Stdout,
			"stderr":    raw.Stderr,
		}
		encoded, err := json.Marshal(envelope)
		if err != nil {
			return fmt.Errorf("encode hook_response envelope: %w", err)
		}
		result = encoded
	}

	ev := protocol.EventSessionHookResponse{
		SessionID: raw.SessionID,
		HookName:  raw.HookName,
		Result:    result,
	}
	return p.sink.OnHookResponse(ev)
}

// ---------------------------------------------------------------------------
// assistant / user / stream_event — raw passthrough.
// ---------------------------------------------------------------------------

// handleAssistant forwards an assistant turn verbatim. The message body is
// preserved as json.RawMessage because the backend Pydantic model owns the
// canonical shape; the bridge has no business reshaping it.
func (p *Parser) handleAssistant(line []byte) error {
	var raw struct {
		SessionID string          `json:"session_id"`
		Message   json.RawMessage `json:"message"`
	}
	if err := json.Unmarshal(line, &raw); err != nil {
		return fmt.Errorf("decode assistant: %w", err)
	}
	ev := protocol.EventSessionAssistant{
		SessionID: raw.SessionID,
		Message:   raw.Message,
	}
	return p.sink.OnAssistant(ev)
}

// handleUser forwards a user turn (typically a tool_result echo from the
// model) verbatim. Same passthrough rationale as handleAssistant.
func (p *Parser) handleUser(line []byte) error {
	var raw struct {
		SessionID string          `json:"session_id"`
		Message   json.RawMessage `json:"message"`
	}
	if err := json.Unmarshal(line, &raw); err != nil {
		return fmt.Errorf("decode user: %w", err)
	}
	ev := protocol.EventSessionUser{
		SessionID: raw.SessionID,
		Message:   raw.Message,
	}
	return p.sink.OnUser(ev)
}

// handleStreamEvent forwards a partial-message delta verbatim. The CLI
// only emits these when --include-partial-messages is on (which the bridge
// always sets). Delta is wrapped as the inner `event` payload so iOS sees
// the same shape it would parse from the CLI directly.
func (p *Parser) handleStreamEvent(line []byte) error {
	var raw struct {
		SessionID string          `json:"session_id"`
		Event     json.RawMessage `json:"event"`
	}
	if err := json.Unmarshal(line, &raw); err != nil {
		return fmt.Errorf("decode stream_event: %w", err)
	}
	ev := protocol.EventSessionStream{
		SessionID: raw.SessionID,
		Delta:     raw.Event,
	}
	return p.sink.OnStream(ev)
}

// ---------------------------------------------------------------------------
// rate_limit_event / result.
// ---------------------------------------------------------------------------

// handleRateLimit decodes a quota snapshot, updates the StreamState, and
// forwards a typed EventSessionRateLimit. The CLI nests the actual fields
// under rate_limit_info using camelCase (resetsAt, rateLimitType…); this
// handler flattens + snake-cases them into the protocol shape.
func (p *Parser) handleRateLimit(line []byte) error {
	var raw struct {
		SessionID     string `json:"session_id"`
		RateLimitInfo struct {
			Status         string `json:"status"`
			RateLimitType  string `json:"rateLimitType"`
			ResetsAt       int64  `json:"resetsAt"`
			OverageStatus  string `json:"overageStatus"`
			IsUsingOverage bool   `json:"isUsingOverage"`
		} `json:"rate_limit_info"`
	}
	if err := json.Unmarshal(line, &raw); err != nil {
		return fmt.Errorf("decode rate_limit_event: %w", err)
	}
	telemetry.ClaudeRateLimitHits.Add(1)

	rl := &RateLimitInfo{
		Status:         raw.RateLimitInfo.Status,
		RateLimitType:  raw.RateLimitInfo.RateLimitType,
		ResetsAt:       raw.RateLimitInfo.ResetsAt,
		OverageStatus:  raw.RateLimitInfo.OverageStatus,
		IsUsingOverage: raw.RateLimitInfo.IsUsingOverage,
	}
	p.state.UpdateRateLimit(rl)

	ev := protocol.EventSessionRateLimit{
		SessionID:      raw.SessionID,
		Status:         rl.Status,
		RateLimitType:  rl.RateLimitType,
		ResetsAt:       rl.ResetsAt,
		OverageStatus:  rl.OverageStatus,
		IsUsingOverage: rl.IsUsingOverage,
	}
	return p.sink.OnRateLimit(ev)
}

// handleResult decodes the once-per-session terminal frame, accumulates
// cost + permission denials onto the StreamState, and forwards the
// flattened EventSessionResult. The CLI uses camelCase for modelUsage and
// nested camelCase for the inner per-model entries; this handler converts
// both to the protocol's snake_case shape.
func (p *Parser) handleResult(line []byte) error {
	var raw struct {
		SessionID         string                      `json:"session_id"`
		DurationMs        int                         `json:"duration_ms"`
		NumTurns          int                         `json:"num_turns"`
		Result            string                      `json:"result"`
		StopReason        string                      `json:"stop_reason"`
		TotalCostUSD      float64                     `json:"total_cost_usd"`
		ModelUsage        map[string]rawCLIModelUsage `json:"modelUsage"`
		PermissionDenials []json.RawMessage           `json:"permission_denials"`
		TerminalReason    string                      `json:"terminal_reason"`
	}
	if err := json.Unmarshal(line, &raw); err != nil {
		return fmt.Errorf("decode result: %w", err)
	}

	p.state.AddCost(raw.TotalCostUSD)
	for _, d := range raw.PermissionDenials {
		p.state.AppendPermissionDenial(d)
	}

	modelUsage := make(map[string]protocol.ModelUsage, len(raw.ModelUsage))
	for model, mu := range raw.ModelUsage {
		modelUsage[model] = protocol.ModelUsage{
			InputTokens:         mu.InputTokens,
			OutputTokens:        mu.OutputTokens,
			CacheReadTokens:     mu.CacheReadInputTokens,
			CacheCreationTokens: mu.CacheCreationInputTokens,
		}
	}

	denials := raw.PermissionDenials
	if denials == nil {
		denials = []json.RawMessage{}
	}

	ev := protocol.EventSessionResult{
		SessionID:         raw.SessionID,
		DurationMs:        raw.DurationMs,
		NumTurns:          raw.NumTurns,
		Result:            raw.Result,
		StopReason:        raw.StopReason,
		TotalCostUSD:      raw.TotalCostUSD,
		ModelUsage:        modelUsage,
		PermissionDenials: denials,
		TerminalReason:    raw.TerminalReason,
	}
	return p.sink.OnResult(ev)
}

// rawCLIModelUsage mirrors the CLI's per-model camelCase block inside
// result.modelUsage. Defined as a named struct (not anonymous) so the
// outer map[string]rawCLIModelUsage decode is straightforward.
type rawCLIModelUsage struct {
	InputTokens              int `json:"inputTokens"`
	OutputTokens             int `json:"outputTokens"`
	CacheReadInputTokens     int `json:"cacheReadInputTokens"`
	CacheCreationInputTokens int `json:"cacheCreationInputTokens"`
}

// ---------------------------------------------------------------------------
// Helpers.
// ---------------------------------------------------------------------------

// promptPreviewMaxLen caps the EventSessionTaskStarted.PromptPreview field
// at a length the iOS chat UI can render without overflowing. Matches the
// Python `build_claude_stream_*` truncation defaults.
const promptPreviewMaxLen = 280

// truncatePrompt returns s shortened to at most max bytes with a single
// trailing ellipsis when truncation occurs. Operates on bytes (not runes)
// because the prompt is already passed through the JSON layer; mid-rune
// cuts are extremely unlikely on the typical English/code prompts and the
// iOS UI tolerates the rare replacement character.
func truncatePrompt(s string, maxLen int) string {
	if len(s) <= maxLen {
		return s
	}
	return s[:maxLen] + "…"
}
