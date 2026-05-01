// Package protocol — envelope and message catalogue tests.
//
// Coverage matrix (per docs/12_Action_Plan_Tasks.md T0.5.4 done criteria):
//
//   - Round-trip marshal/unmarshal for the major message types.
//   - Snake_case JSON tag verification (Pydantic compatibility).
//   - Pydantic fixture decode — JSON literals matching what the Python
//     reference at apps/agent/agent/core/protocol.py would emit must
//     deserialise into the Go structs without loss.
//   - Envelope.Payload (json.RawMessage) byte-for-byte passthrough.
//   - Optional pointer field nil semantics on absent JSON keys.
package protocol

import (
	"bytes"
	"encoding/json"
	"strings"
	"testing"
)

// ---------------------------------------------------------------------------
// Round-trip marshal/unmarshal — table-driven across the major message types.
// ---------------------------------------------------------------------------

func TestRoundTripMarshalUnmarshal(t *testing.T) {
	t.Parallel()

	sessionID := "sess-1"

	tests := []struct {
		name   string
		typ    string
		build  func() (Envelope, error)
		decode func(t *testing.T, raw json.RawMessage)
	}{
		{
			name: "CommandClaudeRun",
			typ:  TypeCommandClaudeRun,
			build: func() (Envelope, error) {
				return NewCommandClaudeRun("session:abc", "corr-1", CommandClaudeRun{
					Prompt:         "implement feature X",
					SessionID:      &sessionID,
					PermissionMode: "acceptEdits",
					AgentTeams:     boolPtr(true),
					ProjectDir:     stringPtr("/Users/a/proj"),
					UserID:         "user-xyz",
				})
			},
			decode: func(t *testing.T, raw json.RawMessage) {
				t.Helper()
				var got CommandClaudeRun
				if err := json.Unmarshal(raw, &got); err != nil {
					t.Fatalf("unmarshal: %v", err)
				}
				if got.Prompt != "implement feature X" {
					t.Errorf("Prompt = %q", got.Prompt)
				}
				if got.SessionID == nil || *got.SessionID != sessionID {
					t.Errorf("SessionID round-trip lost")
				}
				if got.AgentTeams == nil || !*got.AgentTeams {
					t.Errorf("AgentTeams round-trip lost")
				}
				if got.UserID != "user-xyz" {
					t.Errorf("UserID = %q", got.UserID)
				}
			},
		},
		{
			name: "EventSessionInit",
			typ:  TypeEventSessionInit,
			build: func() (Envelope, error) {
				return NewEventSessionInit("session:abc", "corr-1", EventSessionInit{
					SessionID:      sessionID,
					CWD:            "/tmp/work",
					Model:          "claude-sonnet-4",
					Tools:          []string{"Read", "Edit", "Bash"},
					PermissionMode: "acceptEdits",
					APIKeySource:   "none",
					Version:        "0.5.0",
				})
			},
			decode: func(t *testing.T, raw json.RawMessage) {
				t.Helper()
				var got EventSessionInit
				if err := json.Unmarshal(raw, &got); err != nil {
					t.Fatalf("unmarshal: %v", err)
				}
				if got.SessionID != sessionID || got.Model != "claude-sonnet-4" {
					t.Errorf("init fields lost: %+v", got)
				}
				if len(got.Tools) != 3 || got.Tools[2] != "Bash" {
					t.Errorf("Tools round-trip lost: %v", got.Tools)
				}
				if got.APIKeySource != "none" {
					t.Errorf("APIKeySource = %q", got.APIKeySource)
				}
			},
		},
		{
			name: "EventSessionAssistant",
			typ:  TypeEventSessionAssistant,
			build: func() (Envelope, error) {
				inner := json.RawMessage(`{"role":"assistant","content":[{"type":"text","text":"hi"}]}`)
				return NewEventSessionAssistant("session:abc", "corr-1", EventSessionAssistant{
					SessionID: sessionID,
					Message:   inner,
				})
			},
			decode: func(t *testing.T, raw json.RawMessage) {
				t.Helper()
				var got EventSessionAssistant
				if err := json.Unmarshal(raw, &got); err != nil {
					t.Fatalf("unmarshal: %v", err)
				}
				if got.SessionID != sessionID {
					t.Errorf("SessionID = %q", got.SessionID)
				}
				if !bytes.Contains(got.Message, []byte(`"role":"assistant"`)) {
					t.Errorf("Message passthrough lost: %s", string(got.Message))
				}
			},
		},
		{
			name: "EventSessionTaskStarted",
			typ:  TypeEventSessionTaskStarted,
			build: func() (Envelope, error) {
				return NewEventSessionTaskStarted("session:abc", "corr-1", EventSessionTaskStarted{
					SessionID:     sessionID,
					TaskID:        "task-7",
					Description:   "scan repo",
					SubagentType:  "researcher",
					Isolation:     "worktree",
					PromptPreview: "Find all references to X...",
				})
			},
			decode: func(t *testing.T, raw json.RawMessage) {
				t.Helper()
				var got EventSessionTaskStarted
				if err := json.Unmarshal(raw, &got); err != nil {
					t.Fatalf("unmarshal: %v", err)
				}
				if got.TaskID != "task-7" || got.Isolation != "worktree" {
					t.Errorf("task fields lost: %+v", got)
				}
				if got.PromptPreview != "Find all references to X..." {
					t.Errorf("PromptPreview lost")
				}
			},
		},
		{
			name: "EventSessionResult",
			typ:  TypeEventSessionResult,
			build: func() (Envelope, error) {
				return NewEventSessionResult("session:abc", "corr-1", EventSessionResult{
					SessionID:    sessionID,
					DurationMs:   23000,
					NumTurns:     5,
					Result:       "done",
					StopReason:   "end_turn",
					TotalCostUSD: 0.1542,
					ModelUsage: map[string]ModelUsage{
						"claude-sonnet-4": {
							InputTokens:         1200,
							OutputTokens:        450,
							CacheReadTokens:     800,
							CacheCreationTokens: 300,
						},
					},
					PermissionDenials: []json.RawMessage{json.RawMessage(`{"tool":"Bash","reason":"blocked"}`)},
					TerminalReason:    "completed",
				})
			},
			decode: func(t *testing.T, raw json.RawMessage) {
				t.Helper()
				var got EventSessionResult
				if err := json.Unmarshal(raw, &got); err != nil {
					t.Fatalf("unmarshal: %v", err)
				}
				if got.DurationMs != 23000 || got.NumTurns != 5 {
					t.Errorf("scalar fields lost: %+v", got)
				}
				if got.TotalCostUSD < 0.154 || got.TotalCostUSD > 0.155 {
					t.Errorf("TotalCostUSD = %f", got.TotalCostUSD)
				}
				usage, ok := got.ModelUsage["claude-sonnet-4"]
				if !ok {
					t.Fatalf("ModelUsage key missing: %+v", got.ModelUsage)
				}
				if usage.InputTokens != 1200 || usage.CacheReadTokens != 800 {
					t.Errorf("ModelUsage round-trip lost: %+v", usage)
				}
				if len(got.PermissionDenials) != 1 {
					t.Errorf("PermissionDenials length = %d", len(got.PermissionDenials))
				}
			},
		},
		{
			name: "EventUsageReport",
			typ:  TypeEventUsageReport,
			build: func() (Envelope, error) {
				return NewEventUsageReport("", "", EventUsageReport{
					FiveHourPct:      42,
					SevenDayPct:      18,
					FiveHourResetsAt: 1717000000,
					SevenDayResetsAt: 1717604800,
					ReportedAt:       1716998400,
				})
			},
			decode: func(t *testing.T, raw json.RawMessage) {
				t.Helper()
				var got EventUsageReport
				if err := json.Unmarshal(raw, &got); err != nil {
					t.Fatalf("unmarshal: %v", err)
				}
				if got.FiveHourPct != 42 || got.SevenDayPct != 18 {
					t.Errorf("pct fields lost: %+v", got)
				}
				if got.ReportedAt != 1716998400 {
					t.Errorf("ReportedAt lost")
				}
			},
		},
	}

	for _, tc := range tests {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			env, err := tc.build()
			if err != nil {
				t.Fatalf("build: %v", err)
			}
			if env.Type != tc.typ {
				t.Errorf("Type = %q want %q", env.Type, tc.typ)
			}
			if env.ID == "" {
				t.Errorf("ID empty")
			}
			if env.TS == "" {
				t.Errorf("TS empty")
			}

			// Marshal envelope, decode it back, then decode the inner payload.
			wire, err := json.Marshal(env)
			if err != nil {
				t.Fatalf("marshal envelope: %v", err)
			}
			var redecoded Envelope
			if err := json.Unmarshal(wire, &redecoded); err != nil {
				t.Fatalf("unmarshal envelope: %v", err)
			}
			if redecoded.Type != tc.typ || redecoded.ID != env.ID {
				t.Errorf("envelope fields drifted: got %+v want %+v", redecoded, env)
			}
			tc.decode(t, redecoded.Payload)
		})
	}
}

// ---------------------------------------------------------------------------
// Snake_case JSON tag verification — the most user-visible Pydantic contract.
// ---------------------------------------------------------------------------

func TestSnakeCaseJSONTags(t *testing.T) {
	t.Parallel()

	payload := EventSessionTaskStarted{
		SessionID:     "sess-1",
		TaskID:        "task-1",
		Description:   "x",
		SubagentType:  "researcher",
		Isolation:     "worktree",
		PromptPreview: "preview",
	}

	raw, err := json.Marshal(payload)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	got := string(raw)

	wantContains := []string{
		`"session_id"`,
		`"task_id"`,
		`"subagent_type"`,
		`"prompt_preview"`,
	}
	for _, want := range wantContains {
		if !strings.Contains(got, want) {
			t.Errorf("missing %s in %s", want, got)
		}
	}

	mustNotContain := []string{
		`"sessionId"`,
		`"taskId"`,
		`"subagentType"`,
		`"promptPreview"`,
	}
	for _, bad := range mustNotContain {
		if strings.Contains(got, bad) {
			t.Errorf("found camelCase %s in %s", bad, got)
		}
	}
}

// ---------------------------------------------------------------------------
// Pydantic compatibility — JSON literals shaped like what the Python
// reference (apps/agent/agent/core/protocol.py) would produce must decode
// cleanly into the Go structs. This is the explicit T0.5.4 fidelity check.
// ---------------------------------------------------------------------------

func TestPydanticFixture_CommandClaudeRun(t *testing.T) {
	t.Parallel()

	// Pydantic default: model_dump_json() emits snake_case keys; optional
	// fields default to nil pointers when absent.
	fixture := []byte(`{
		"prompt": "fix the bug",
		"session_id": "sess-42",
		"permission_mode": "default",
		"agent_teams": false,
		"project_dir": "/Users/a/repo",
		"user_id": "user-1"
	}`)

	var got CommandClaudeRun
	if err := json.Unmarshal(fixture, &got); err != nil {
		t.Fatalf("decode pydantic fixture: %v", err)
	}
	if got.Prompt != "fix the bug" {
		t.Errorf("Prompt = %q", got.Prompt)
	}
	if got.SessionID == nil || *got.SessionID != "sess-42" {
		t.Errorf("SessionID = %v", got.SessionID)
	}
	if got.PermissionMode != "default" {
		t.Errorf("PermissionMode = %q", got.PermissionMode)
	}
	if got.AgentTeams == nil || *got.AgentTeams {
		t.Errorf("AgentTeams = %v", got.AgentTeams)
	}
	if got.ProjectDir == nil || *got.ProjectDir != "/Users/a/repo" {
		t.Errorf("ProjectDir = %v", got.ProjectDir)
	}
	if got.UserID != "user-1" {
		t.Errorf("UserID = %q", got.UserID)
	}
}

func TestPydanticFixture_EventSessionTaskStarted(t *testing.T) {
	t.Parallel()

	fixture := []byte(`{
		"session_id": "sess-42",
		"task_id": "abc-123",
		"description": "research repo layout",
		"subagent_type": "researcher",
		"isolation": "worktree",
		"prompt_preview": "Look up the foo/bar module..."
	}`)

	var got EventSessionTaskStarted
	if err := json.Unmarshal(fixture, &got); err != nil {
		t.Fatalf("decode pydantic fixture: %v", err)
	}
	if got.SessionID != "sess-42" || got.TaskID != "abc-123" {
		t.Errorf("ids lost: %+v", got)
	}
	if got.SubagentType != "researcher" || got.Isolation != "worktree" {
		t.Errorf("classification fields lost: %+v", got)
	}
	if got.PromptPreview != "Look up the foo/bar module..." {
		t.Errorf("PromptPreview lost: %q", got.PromptPreview)
	}
}

func TestPydanticFixture_EventSessionResult(t *testing.T) {
	t.Parallel()

	fixture := []byte(`{
		"session_id": "sess-42",
		"duration_ms": 18230,
		"num_turns": 3,
		"result": "ok",
		"stop_reason": "end_turn",
		"total_cost_usd": 0.0421,
		"model_usage": {
			"claude-sonnet-4": {
				"input_tokens": 800,
				"output_tokens": 320,
				"cache_read_input_tokens": 1200,
				"cache_creation_input_tokens": 200
			}
		},
		"permission_denials": [],
		"terminal_reason": "completed"
	}`)

	var got EventSessionResult
	if err := json.Unmarshal(fixture, &got); err != nil {
		t.Fatalf("decode pydantic fixture: %v", err)
	}
	if got.DurationMs != 18230 || got.NumTurns != 3 {
		t.Errorf("scalars lost: %+v", got)
	}
	if got.TotalCostUSD < 0.042 || got.TotalCostUSD > 0.043 {
		t.Errorf("TotalCostUSD = %f", got.TotalCostUSD)
	}
	usage, ok := got.ModelUsage["claude-sonnet-4"]
	if !ok {
		t.Fatalf("model_usage key missing: %+v", got.ModelUsage)
	}
	if usage.InputTokens != 800 || usage.OutputTokens != 320 {
		t.Errorf("usage tokens lost: %+v", usage)
	}
	if usage.CacheReadTokens != 1200 || usage.CacheCreationTokens != 200 {
		t.Errorf("usage cache tokens lost: %+v", usage)
	}
	if got.PermissionDenials == nil {
		t.Errorf("PermissionDenials should decode to non-nil empty slice")
	}
	if got.TerminalReason != "completed" {
		t.Errorf("TerminalReason = %q", got.TerminalReason)
	}
}

// ---------------------------------------------------------------------------
// Envelope.Payload byte-for-byte passthrough.
// ---------------------------------------------------------------------------

func TestEnvelopePayloadPassthrough(t *testing.T) {
	t.Parallel()

	// A payload with whitespace-sensitive content: nested raw with float.
	// json.Marshal compacts the bytes, so we use the compacted form for
	// comparison. The point is round-trip equivalence, not source equality.
	innerSrc := json.RawMessage(`{"role":"assistant","content":[{"type":"text","text":"hello"}]}`)
	env, err := NewEventSessionAssistant("session:abc", "corr-1", EventSessionAssistant{
		SessionID: "sess-1",
		Message:   innerSrc,
	})
	if err != nil {
		t.Fatalf("build: %v", err)
	}

	wire, err := json.Marshal(env)
	if err != nil {
		t.Fatalf("marshal envelope: %v", err)
	}
	var decoded Envelope
	if err := json.Unmarshal(wire, &decoded); err != nil {
		t.Fatalf("unmarshal envelope: %v", err)
	}

	var msg EventSessionAssistant
	if err := json.Unmarshal(decoded.Payload, &msg); err != nil {
		t.Fatalf("unmarshal payload: %v", err)
	}

	// Compact both and compare byte-for-byte — proves no double-encoding or
	// mutation of the inner JSON.
	wantCompact := compact(t, innerSrc)
	gotCompact := compact(t, msg.Message)
	if !bytes.Equal(wantCompact, gotCompact) {
		t.Errorf("inner payload mutated:\nwant %s\ngot  %s", wantCompact, gotCompact)
	}
}

// ---------------------------------------------------------------------------
// Optional pointer fields → nil semantics on absent JSON keys.
// ---------------------------------------------------------------------------

func TestOptionalPointerFieldsAbsent(t *testing.T) {
	t.Parallel()

	// Only `prompt` and `user_id` (required) supplied.
	fixture := []byte(`{"prompt": "do work", "user_id": "u1"}`)

	var got CommandClaudeRun
	if err := json.Unmarshal(fixture, &got); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if got.SessionID != nil {
		t.Errorf("SessionID should be nil, got %v", *got.SessionID)
	}
	if got.AgentTeams != nil {
		t.Errorf("AgentTeams should be nil, got %v", *got.AgentTeams)
	}
	if got.ProjectDir != nil {
		t.Errorf("ProjectDir should be nil, got %v", *got.ProjectDir)
	}
	if got.PermissionMode != "" {
		t.Errorf("PermissionMode should be zero, got %q", got.PermissionMode)
	}
}

// ---------------------------------------------------------------------------
// Helpers.
// ---------------------------------------------------------------------------

func boolPtr(b bool) *bool       { return &b }
func stringPtr(s string) *string { return &s }

func compact(t *testing.T, raw json.RawMessage) []byte {
	t.Helper()
	var buf bytes.Buffer
	if err := json.Compact(&buf, raw); err != nil {
		t.Fatalf("compact: %v", err)
	}
	return buf.Bytes()
}
