// Package claude — stream-state tracking.
//
// StreamState mirrors apps/agent/agent/runners/claude_runner.py's
// `_StreamState` (the legacy Python host agent) but extends it with the
// fields required by docs/11_Bridge_Spec.md §6: subagent map, rate-limit
// snapshot, cumulative cost, and permission denials. The state is an
// internal companion to Parser — it captures the longitudinal view of a
// single `claude -p` run that the per-event EventSink callbacks cannot
// express on their own.
//
// Concurrency: every accessor takes a mutex. The Parser dispatch loop is
// single-goroutine in production (one Parser per subprocess), but tests
// in T0.5.6 hammer the same StreamState from many goroutines under
// `go test -race` to flush out future regressions when a Reporter or
// statusline poller is added in later tasks.

package claude

import (
	"encoding/json"
	"sync"
	"time"
)

// SubagentState captures a single sub-agent task spawned via the Agent
// Teams flow. Lifecycle: created on system/task_started, mutated on
// system/task_progress (out-of-band; not shown here), finalised on
// system/task_notification at which point the entry is moved from
// ActiveSubagents to CompletedSubagents.
type SubagentState struct {
	TaskID       string
	Description  string
	SubagentType string
	Isolation    string
	Prompt       string
	StartedAt    time.Time
	CompletedAt  *time.Time
	// Status is one of "active", "completed", "failed". Mirrors the
	// task_notification.status string verbatim once finalised.
	Status string
	Usage  *SubagentUsage
}

// SubagentUsage is the per-subagent token/tool-use accounting reported in
// task_notification.usage. Field names use Go-idiomatic camelCase since
// SubagentUsage is internal — the JSON projection happens at the
// EventSink boundary, not on this type.
type SubagentUsage struct {
	InputTokens  int
	OutputTokens int
	CacheRead    int
	CacheWrite   int
	TotalTokens  int
	ToolUses     int
	DurationMs   int
}

// RateLimitInfo is the most recent `rate_limit_event.rate_limit_info`
// payload observed on the stream. Stored on the state so a long-running
// session can be polled for its current quota status without rescanning
// the historical event log.
type RateLimitInfo struct {
	Status         string // "allowed" | "warning" | "exceeded"
	RateLimitType  string // typically "five_hour"
	ResetsAt       int64  // epoch seconds — when the current window resets
	OverageStatus  string
	IsUsingOverage bool
}

// StreamState is the parser's per-run scratch pad. Field semantics:
//
//   - SessionID/Model/PermissionMode/APIKeySource: captured from system/init
//     and never mutated thereafter (single init per stream).
//   - ActiveSubagents: keyed by Anthropic-assigned task_id; entries removed
//     on completion via CompleteSubagent.
//   - CompletedSubagents: append-only history slice ordered by completion
//     time. Holds value copies so the original SubagentState pointer can
//     be GC'd if nothing else retains it.
//   - RateLimitInfo: last-write-wins; nil until the first rate_limit_event.
//   - TotalCostUSD: accumulated across the stream from result.total_cost_usd.
//     The current claude CLI emits result at most once per session, so this
//     is effectively a single-write field — the Add semantics future-proof
//     against streams that fan in multiple result frames.
//   - PermissionDenials: raw passthrough so the backend can decode against
//     its own Pydantic schema without the bridge committing to a shape.
type StreamState struct {
	SessionID      string
	Model          string
	PermissionMode string
	APIKeySource   string

	ActiveSubagents    map[string]*SubagentState
	CompletedSubagents []SubagentState

	RateLimitInfo     *RateLimitInfo
	TotalCostUSD      float64
	PermissionDenials []json.RawMessage

	// resultObserved is true once the parser has dispatched at least
	// one terminal `result` frame. Used by the V1.x supervisor to
	// distinguish "claude exited 0 + Result emitted" from "claude
	// exited 0 but stream-json never produced a result frame".
	resultObserved bool

	mu sync.Mutex
}

// HasResult reports whether the parser has observed a terminal
// `result` stream-json frame. Set by AddCost (which is the canonical
// per-result entry point). Used by the V1.x Claude Subprocess
// Supervisor to drive the completed-vs-soft-anomaly distinction on
// Unregister.
func (s *StreamState) HasResult() bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.resultObserved
}

// NewStreamState constructs a StreamState with non-nil maps/slices so the
// caller can write into them without an explicit init step.
func NewStreamState() *StreamState {
	return &StreamState{
		ActiveSubagents:    make(map[string]*SubagentState),
		CompletedSubagents: make([]SubagentState, 0),
		PermissionDenials:  make([]json.RawMessage, 0),
	}
}

// SetSessionMeta records the once-per-stream session metadata captured from
// system/init. Subsequent calls overwrite — defensible since claude only
// emits init once per run, and the bridge owns one Parser per run.
func (s *StreamState) SetSessionMeta(sessionID, model, permissionMode, apiKeySource string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.SessionID = sessionID
	s.Model = model
	s.PermissionMode = permissionMode
	s.APIKeySource = apiKeySource
}

// RegisterSubagent inserts a new subagent into the active map. If a task
// with the same TaskID already exists (anomalous — claude does not reuse
// task_ids within a session), the older entry is overwritten. The pointer
// is retained so subsequent mutations (e.g. progress updates if added in
// a later task) propagate without a re-lookup.
func (s *StreamState) RegisterSubagent(sub *SubagentState) {
	if sub == nil {
		return
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	s.ActiveSubagents[sub.TaskID] = sub
}

// CompleteSubagent transitions a subagent from Active → Completed, writes
// the terminal status + usage onto the SubagentState, appends a value copy
// to CompletedSubagents, and removes the entry from the active map.
//
// Returns the now-finalised SubagentState (value, not pointer) so callers
// can build downstream events (e.g. EventSessionTaskNotification) from a
// stable snapshot. If the task_id is unknown — observed in practice when
// the upstream stream replays an old notification — a synthetic completion
// entry is created so the historical record stays consistent.
func (s *StreamState) CompleteSubagent(taskID, status string, usage *SubagentUsage) SubagentState {
	s.mu.Lock()
	defer s.mu.Unlock()

	now := time.Now()
	sub, ok := s.ActiveSubagents[taskID]
	if !ok {
		sub = &SubagentState{
			TaskID:    taskID,
			StartedAt: now,
		}
	}
	sub.Status = status
	sub.Usage = usage
	sub.CompletedAt = &now

	// Move into the completion history as a value copy so callers cannot
	// race against future mutations on the original pointer.
	completed := *sub
	s.CompletedSubagents = append(s.CompletedSubagents, completed)
	delete(s.ActiveSubagents, taskID)

	return completed
}

// UpdateRateLimit replaces the cached RateLimitInfo with the latest
// snapshot from a rate_limit_event. Concurrent reads via SnapshotRateLimit
// observe a consistent value because the field is updated under the mutex.
func (s *StreamState) UpdateRateLimit(rl *RateLimitInfo) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.RateLimitInfo = rl
}

// AddCost increments TotalCostUSD by amount. Called from the result frame
// handler; uses Add semantics (rather than Set) so streams that ever emit
// multiple result frames accumulate cleanly.
func (s *StreamState) AddCost(amount float64) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.TotalCostUSD += amount
	s.resultObserved = true
}

// AppendPermissionDenial appends a raw permission denial payload to the
// state. Stored verbatim because the backend owns the schema; the bridge
// is just a multiplexer.
func (s *StreamState) AppendPermissionDenial(raw json.RawMessage) {
	if len(raw) == 0 {
		return
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	// Defensive copy — json.RawMessage aliases the caller's slice and we
	// must not retain a reference into the parser's buffer.
	cp := make(json.RawMessage, len(raw))
	copy(cp, raw)
	s.PermissionDenials = append(s.PermissionDenials, cp)
}

// SnapshotActiveSubagents returns a shallow copy of the active subagent
// map. Used by tests and future status endpoints; the production parser
// dispatch loop never reads its own state.
func (s *StreamState) SnapshotActiveSubagents() map[string]SubagentState {
	s.mu.Lock()
	defer s.mu.Unlock()
	out := make(map[string]SubagentState, len(s.ActiveSubagents))
	for k, v := range s.ActiveSubagents {
		out[k] = *v
	}
	return out
}

// SnapshotCompletedSubagents returns a copy of the completed history
// slice so callers can iterate without holding the state mutex.
func (s *StreamState) SnapshotCompletedSubagents() []SubagentState {
	s.mu.Lock()
	defer s.mu.Unlock()
	out := make([]SubagentState, len(s.CompletedSubagents))
	copy(out, s.CompletedSubagents)
	return out
}

// SnapshotRateLimit returns the current RateLimitInfo (or nil) under the
// state mutex.
func (s *StreamState) SnapshotRateLimit() *RateLimitInfo {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.RateLimitInfo == nil {
		return nil
	}
	rl := *s.RateLimitInfo
	return &rl
}

// SnapshotCost returns the current TotalCostUSD under the state mutex.
func (s *StreamState) SnapshotCost() float64 {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.TotalCostUSD
}
