package claude

import (
	"encoding/json"
	"io"
	"log/slog"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"sync/atomic"
	"testing"

	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/protocol"
)

// ---------------------------------------------------------------------------
// mockSink — a configurable EventSink whose every method dispatches to an
// optional per-method hook. Methods left nil count invocations only,
// returning nil. Used by every parser_test.go test below.
// ---------------------------------------------------------------------------

type mockSink struct {
	mu sync.Mutex

	OnInitFn             func(protocol.EventSessionInit) error
	OnAssistantFn        func(protocol.EventSessionAssistant) error
	OnUserFn             func(protocol.EventSessionUser) error
	OnStreamFn           func(protocol.EventSessionStream) error
	OnTaskStartedFn      func(protocol.EventSessionTaskStarted) error
	OnTaskProgressFn     func(protocol.EventSessionTaskProgress) error
	OnTaskNotificationFn func(protocol.EventSessionTaskNotification) error
	OnRateLimitFn        func(protocol.EventSessionRateLimit) error
	OnHookStartedFn      func(protocol.EventSessionHookStarted) error
	OnHookResponseFn     func(protocol.EventSessionHookResponse) error
	OnResultFn           func(protocol.EventSessionResult) error
}

func (m *mockSink) OnInit(ev protocol.EventSessionInit) error {
	m.mu.Lock()
	fn := m.OnInitFn
	m.mu.Unlock()
	if fn != nil {
		return fn(ev)
	}
	return nil
}

func (m *mockSink) OnAssistant(ev protocol.EventSessionAssistant) error {
	m.mu.Lock()
	fn := m.OnAssistantFn
	m.mu.Unlock()
	if fn != nil {
		return fn(ev)
	}
	return nil
}

func (m *mockSink) OnUser(ev protocol.EventSessionUser) error {
	m.mu.Lock()
	fn := m.OnUserFn
	m.mu.Unlock()
	if fn != nil {
		return fn(ev)
	}
	return nil
}

func (m *mockSink) OnStream(ev protocol.EventSessionStream) error {
	m.mu.Lock()
	fn := m.OnStreamFn
	m.mu.Unlock()
	if fn != nil {
		return fn(ev)
	}
	return nil
}

func (m *mockSink) OnTaskStarted(ev protocol.EventSessionTaskStarted) error {
	m.mu.Lock()
	fn := m.OnTaskStartedFn
	m.mu.Unlock()
	if fn != nil {
		return fn(ev)
	}
	return nil
}

func (m *mockSink) OnTaskProgress(ev protocol.EventSessionTaskProgress) error {
	m.mu.Lock()
	fn := m.OnTaskProgressFn
	m.mu.Unlock()
	if fn != nil {
		return fn(ev)
	}
	return nil
}

func (m *mockSink) OnTaskNotification(ev protocol.EventSessionTaskNotification) error {
	m.mu.Lock()
	fn := m.OnTaskNotificationFn
	m.mu.Unlock()
	if fn != nil {
		return fn(ev)
	}
	return nil
}

func (m *mockSink) OnRateLimit(ev protocol.EventSessionRateLimit) error {
	m.mu.Lock()
	fn := m.OnRateLimitFn
	m.mu.Unlock()
	if fn != nil {
		return fn(ev)
	}
	return nil
}

func (m *mockSink) OnHookStarted(ev protocol.EventSessionHookStarted) error {
	m.mu.Lock()
	fn := m.OnHookStartedFn
	m.mu.Unlock()
	if fn != nil {
		return fn(ev)
	}
	return nil
}

func (m *mockSink) OnHookResponse(ev protocol.EventSessionHookResponse) error {
	m.mu.Lock()
	fn := m.OnHookResponseFn
	m.mu.Unlock()
	if fn != nil {
		return fn(ev)
	}
	return nil
}

func (m *mockSink) OnResult(ev protocol.EventSessionResult) error {
	m.mu.Lock()
	fn := m.OnResultFn
	m.mu.Unlock()
	if fn != nil {
		return fn(ev)
	}
	return nil
}

// discardLogger returns a slog.Logger that drops every record. Tests rely
// on assertions against the EventSink, not on log output.
func discardLogger() *slog.Logger {
	return slog.New(slog.NewTextHandler(io.Discard, nil))
}

// ---------------------------------------------------------------------------
// TestParser_AgentTeams — end-to-end parse against the spike fixture.
// The fixture (~/Code/claude-teams-spike/results/02-agent-teams/run-1.jsonl)
// captures three subagents spawned + finalised; this asserts the parser
// recognises every task_started/task_notification pair and that the
// init frame surfaces as well.
// ---------------------------------------------------------------------------

func TestParser_AgentTeams(t *testing.T) {
	t.Parallel()

	path := filepath.Join("testdata", "02-agent-teams.jsonl")
	f, err := os.Open(path)
	if err != nil {
		t.Fatalf("open fixture: %v", err)
	}
	t.Cleanup(func() { _ = f.Close() })

	var (
		initCount         atomic.Int32
		startedCount      atomic.Int32
		notificationCount atomic.Int32
		progressCount     atomic.Int32
		hookStartedCount  atomic.Int32
		hookResponseCount atomic.Int32
		assistantCount    atomic.Int32
		userCount         atomic.Int32
		streamCount       atomic.Int32
		rateLimitCount    atomic.Int32
	)

	sink := &mockSink{
		OnInitFn:             func(protocol.EventSessionInit) error { initCount.Add(1); return nil },
		OnTaskStartedFn:      func(protocol.EventSessionTaskStarted) error { startedCount.Add(1); return nil },
		OnTaskNotificationFn: func(protocol.EventSessionTaskNotification) error { notificationCount.Add(1); return nil },
		OnTaskProgressFn:     func(protocol.EventSessionTaskProgress) error { progressCount.Add(1); return nil },
		OnHookStartedFn:      func(protocol.EventSessionHookStarted) error { hookStartedCount.Add(1); return nil },
		OnHookResponseFn:     func(protocol.EventSessionHookResponse) error { hookResponseCount.Add(1); return nil },
		OnAssistantFn:        func(protocol.EventSessionAssistant) error { assistantCount.Add(1); return nil },
		OnUserFn:             func(protocol.EventSessionUser) error { userCount.Add(1); return nil },
		OnStreamFn:           func(protocol.EventSessionStream) error { streamCount.Add(1); return nil },
		OnRateLimitFn:        func(protocol.EventSessionRateLimit) error { rateLimitCount.Add(1); return nil },
	}

	p := NewParser(sink, discardLogger())
	if err := p.Parse(f); err != nil {
		t.Fatalf("Parse: %v", err)
	}

	// Done-criteria asserts: 3 task_started + 3 task_notification per
	// docs/12_Action_Plan_Tasks.md T0.5.6.
	if got := startedCount.Load(); got != 3 {
		t.Errorf("task_started count: want 3, got %d", got)
	}
	if got := notificationCount.Load(); got != 3 {
		t.Errorf("task_notification count: want 3, got %d", got)
	}
	if got := initCount.Load(); got != 1 {
		t.Errorf("init count: want 1, got %d", got)
	}

	// Light sanity on the higher-volume frames so a future fixture swap
	// or schema drift surfaces a meaningful failure rather than a silent
	// regression.
	if got := progressCount.Load(); got != 50 {
		t.Errorf("task_progress count: want 50, got %d", got)
	}
	if got := hookStartedCount.Load(); got != 34 {
		t.Errorf("hook_started count: want 34, got %d", got)
	}
	if got := hookResponseCount.Load(); got != 34 {
		t.Errorf("hook_response count: want 34, got %d", got)
	}
	if got := rateLimitCount.Load(); got != 1 {
		t.Errorf("rate_limit_event count: want 1, got %d", got)
	}
	if assistantCount.Load() == 0 {
		t.Errorf("assistant count: want > 0, got 0")
	}
	if userCount.Load() == 0 {
		t.Errorf("user count: want > 0, got 0")
	}
	if streamCount.Load() == 0 {
		t.Errorf("stream_event count: want > 0, got 0")
	}
}

// ---------------------------------------------------------------------------
// TestParser_StatePopulatedAfterFullStream — the fixture parse must
// finalise three subagents into CompletedSubagents and clear the active
// map. Cost stays zero because run-1 has no result frame.
// ---------------------------------------------------------------------------

func TestParser_StatePopulatedAfterFullStream(t *testing.T) {
	t.Parallel()

	path := filepath.Join("testdata", "02-agent-teams.jsonl")
	f, err := os.Open(path)
	if err != nil {
		t.Fatalf("open fixture: %v", err)
	}
	t.Cleanup(func() { _ = f.Close() })

	p := NewParser(&mockSink{}, discardLogger())
	if err := p.Parse(f); err != nil {
		t.Fatalf("Parse: %v", err)
	}

	st := p.State()

	if got := len(st.SnapshotActiveSubagents()); got != 0 {
		t.Errorf("active subagents after parse: want 0, got %d", got)
	}
	if got := len(st.SnapshotCompletedSubagents()); got != 3 {
		t.Errorf("completed subagents: want 3, got %d", got)
	}

	completed := st.SnapshotCompletedSubagents()
	for i, sub := range completed {
		if sub.TaskID == "" {
			t.Errorf("completed[%d]: empty TaskID", i)
		}
		if sub.Status == "" {
			t.Errorf("completed[%d]: empty Status", i)
		}
		if sub.Usage == nil {
			t.Errorf("completed[%d]: nil Usage", i)
			continue
		}
		// run-1 fixture: every subagent reports a non-zero token total.
		if sub.Usage.TotalTokens == 0 {
			t.Errorf("completed[%d]: TotalTokens unexpectedly 0", i)
		}
	}

	// Session metadata captured from the single init frame.
	if st.SessionID == "" {
		t.Errorf("StreamState.SessionID: want non-empty, got %q", st.SessionID)
	}

	// Rate limit: fixture has one allowed/five_hour event.
	rl := st.SnapshotRateLimit()
	if rl == nil {
		t.Fatalf("rate limit snapshot: want non-nil, got nil")
	}
	if rl.Status != "allowed" {
		t.Errorf("rate limit status: want allowed, got %q", rl.Status)
	}
	if rl.RateLimitType != "five_hour" {
		t.Errorf("rate limit type: want five_hour, got %q", rl.RateLimitType)
	}

	// run-1 has no result frame → cost stays at 0.
	if got := st.SnapshotCost(); got != 0 {
		t.Errorf("TotalCostUSD: want 0 (no result frame in fixture), got %v", got)
	}
}

// ---------------------------------------------------------------------------
// TestParser_MalformedJSONLine — a bad line in the middle of the stream
// must be logged and skipped; subsequent valid lines must still dispatch.
// ---------------------------------------------------------------------------

func TestParser_MalformedJSONLine(t *testing.T) {
	t.Parallel()

	input := strings.NewReader(
		`{"type":"system","subtype":"init","session_id":"a","cwd":"/x","model":"m","tools":[]}` + "\n" +
			`not valid json` + "\n" +
			`{"type":"result","session_id":"a","total_cost_usd":0.5}` + "\n",
	)

	var (
		initCalled   atomic.Bool
		resultCalled atomic.Bool
	)
	sink := &mockSink{
		OnInitFn:   func(protocol.EventSessionInit) error { initCalled.Store(true); return nil },
		OnResultFn: func(protocol.EventSessionResult) error { resultCalled.Store(true); return nil },
	}

	p := NewParser(sink, discardLogger())
	if err := p.Parse(input); err != nil {
		t.Fatalf("Parse: %v", err)
	}

	if !initCalled.Load() {
		t.Errorf("init: not invoked despite valid first line")
	}
	if !resultCalled.Load() {
		t.Errorf("result: not invoked — parser stopped after malformed line")
	}

	// Cost from the result line should have flowed into the state too.
	if got := p.State().SnapshotCost(); got != 0.5 {
		t.Errorf("cost after parse: want 0.5, got %v", got)
	}
}

// ---------------------------------------------------------------------------
// TestParser_TaskAliasApplied — synthetic frame with subagent_type "Task"
// must NOT canonicalise the label (subagent_type is a free-form label per
// the Python reference, not a tool name). Init.tools[] DOES get aliased
// since those ARE tool names.
// ---------------------------------------------------------------------------

func TestParser_TaskAliasApplied(t *testing.T) {
	t.Parallel()

	input := strings.NewReader(
		`{"type":"system","subtype":"init","session_id":"x","cwd":"/x","model":"m","tools":["Task","Bash"]}` + "\n" +
			`{"type":"system","subtype":"task_started","session_id":"x","task_id":"t1","subagent_type":"Task","prompt":"p"}` + "\n",
	)

	var capturedInit protocol.EventSessionInit
	var capturedStart protocol.EventSessionTaskStarted
	sink := &mockSink{
		OnInitFn: func(ev protocol.EventSessionInit) error {
			capturedInit = ev
			return nil
		},
		OnTaskStartedFn: func(ev protocol.EventSessionTaskStarted) error {
			capturedStart = ev
			return nil
		},
	}

	p := NewParser(sink, discardLogger())
	if err := p.Parse(input); err != nil {
		t.Fatalf("Parse: %v", err)
	}

	// init.tools[] entries must canonicalise: Task → Agent.
	if len(capturedInit.Tools) != 2 {
		t.Fatalf("init.tools length: want 2, got %d", len(capturedInit.Tools))
	}
	if capturedInit.Tools[0] != "Agent" {
		t.Errorf("init.tools[0]: want Agent (canonicalised), got %q", capturedInit.Tools[0])
	}
	if capturedInit.Tools[1] != "Bash" {
		t.Errorf("init.tools[1]: want Bash (passthrough), got %q", capturedInit.Tools[1])
	}

	// task_started.subagent_type is a label and must pass through verbatim.
	if capturedStart.SubagentType != "Task" {
		t.Errorf("task_started.subagent_type: want Task (label, no aliasing), got %q", capturedStart.SubagentType)
	}
}

// ---------------------------------------------------------------------------
// TestParser_RateLimitFlattens — verifies camelCase → snake_case mapping
// for the rate_limit_event nested payload.
// ---------------------------------------------------------------------------

func TestParser_RateLimitFlattens(t *testing.T) {
	t.Parallel()

	input := strings.NewReader(
		`{"type":"rate_limit_event","session_id":"x","rate_limit_info":{"status":"warning","rateLimitType":"five_hour","resetsAt":1777657800,"overageStatus":"allowed","isUsingOverage":false}}` + "\n",
	)

	var captured protocol.EventSessionRateLimit
	sink := &mockSink{
		OnRateLimitFn: func(ev protocol.EventSessionRateLimit) error {
			captured = ev
			return nil
		},
	}

	p := NewParser(sink, discardLogger())
	if err := p.Parse(input); err != nil {
		t.Fatalf("Parse: %v", err)
	}

	if captured.Status != "warning" {
		t.Errorf("status: want warning, got %q", captured.Status)
	}
	if captured.RateLimitType != "five_hour" {
		t.Errorf("rate_limit_type: want five_hour, got %q", captured.RateLimitType)
	}
	if captured.ResetsAt != 1777657800 {
		t.Errorf("resets_at: want 1777657800, got %d", captured.ResetsAt)
	}
	if captured.OverageStatus != "allowed" {
		t.Errorf("overage_status: want allowed, got %q", captured.OverageStatus)
	}
	if captured.IsUsingOverage {
		t.Errorf("is_using_overage: want false, got true")
	}
}

// ---------------------------------------------------------------------------
// TestParser_ResultModelUsageFlattens — verifies the camelCase modelUsage
// CLI shape is mapped to the protocol's snake_case ModelUsage.
// ---------------------------------------------------------------------------

func TestParser_ResultModelUsageFlattens(t *testing.T) {
	t.Parallel()

	input := strings.NewReader(
		`{"type":"result","session_id":"x","duration_ms":2276,"num_turns":1,"result":"hi","stop_reason":"end_turn","total_cost_usd":0.07,"modelUsage":{"claude-opus-4-7":{"inputTokens":6,"outputTokens":11,"cacheReadInputTokens":15731,"cacheCreationInputTokens":11139}},"permission_denials":[],"terminal_reason":"completed"}` + "\n",
	)

	var captured protocol.EventSessionResult
	sink := &mockSink{
		OnResultFn: func(ev protocol.EventSessionResult) error {
			captured = ev
			return nil
		},
	}

	p := NewParser(sink, discardLogger())
	if err := p.Parse(input); err != nil {
		t.Fatalf("Parse: %v", err)
	}

	mu, ok := captured.ModelUsage["claude-opus-4-7"]
	if !ok {
		t.Fatalf("modelUsage entry for claude-opus-4-7 missing; got keys: %v", keysOf(captured.ModelUsage))
	}
	if mu.InputTokens != 6 {
		t.Errorf("input_tokens: want 6, got %d", mu.InputTokens)
	}
	if mu.OutputTokens != 11 {
		t.Errorf("output_tokens: want 11, got %d", mu.OutputTokens)
	}
	if mu.CacheReadTokens != 15731 {
		t.Errorf("cache_read_input_tokens: want 15731, got %d", mu.CacheReadTokens)
	}
	if mu.CacheCreationTokens != 11139 {
		t.Errorf("cache_creation_input_tokens: want 11139, got %d", mu.CacheCreationTokens)
	}
	if captured.TotalCostUSD != 0.07 {
		t.Errorf("total_cost_usd: want 0.07, got %v", captured.TotalCostUSD)
	}
}

func keysOf(m map[string]protocol.ModelUsage) []string {
	out := make([]string, 0, len(m))
	for k := range m {
		out = append(out, k)
	}
	return out
}

// ---------------------------------------------------------------------------
// TestStreamState_ConcurrentSafe — exercise the StreamState mutex from
// many goroutines. Must run clean under -race; any data race surfaces as
// a t.Fatal because the race detector aborts the test process.
// ---------------------------------------------------------------------------

func TestStreamState_ConcurrentSafe(t *testing.T) {
	t.Parallel()

	const goroutines = 100
	st := NewStreamState()

	var wg sync.WaitGroup
	wg.Add(goroutines)
	for i := 0; i < goroutines; i++ {
		go func(idx int) {
			defer wg.Done()
			taskID := "t-" + strings.Repeat("x", idx%5+1)
			st.RegisterSubagent(&SubagentState{
				TaskID:       taskID,
				SubagentType: "general-purpose",
				Status:       "active",
			})
			st.UpdateRateLimit(&RateLimitInfo{
				Status:        "allowed",
				RateLimitType: "five_hour",
				ResetsAt:      int64(idx),
			})
			st.AddCost(0.001)
			st.AppendPermissionDenial(json.RawMessage(`{"tool":"Bash"}`))
			st.CompleteSubagent(taskID, "completed", &SubagentUsage{TotalTokens: idx})
			// Snapshot accessors must also be safe.
			_ = st.SnapshotActiveSubagents()
			_ = st.SnapshotCompletedSubagents()
			_ = st.SnapshotRateLimit()
			_ = st.SnapshotCost()
		}(i)
	}
	wg.Wait()

	// Cost was added 100x; floating-point sum is deterministic-enough for
	// a coarse equality check.
	if got := st.SnapshotCost(); got < 0.099 || got > 0.101 {
		t.Errorf("TotalCostUSD after 100 adds of 0.001: want ≈0.1, got %v", got)
	}
	if got := len(st.PermissionDenials); got != goroutines {
		t.Errorf("permission denials count: want %d, got %d", goroutines, got)
	}
}
