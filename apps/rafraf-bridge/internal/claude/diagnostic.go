// Package claude — V1.x supervisor diagnostic spawn helper.
//
// When a supervised instance enters the `stale` state and the
// rate-limit cache is clean, the supervisor fires a one-shot
// diagnostic claude with `--max-tokens 500` (default; clamped per
// SupervisorConfig.DiagnosticMaxTokens) to ask "what went wrong?"
// using the failed instance's stderr tail + last stdout context as
// the prompt.
//
// Hard guarantees (per spec §8 cost guard):
//
//   - Recursion depth ≤ 1, enforced via Supervisor.diagnosticDepth
//     atomic.Int32 CAS(0, 1). A second concurrent stale never spawns
//     a second diagnostic.
//   - Per-spawn timeout = cfg.DiagnosticTimeout (default 30s).
//   - --max-tokens always present in argv (cost guard).
//   - Diagnostic spawn deliberately bypasses the V1.3 permission
//     broker overlay — no PreToolUse hook for diagnostics.
//
// On success the supervisor emits `event.claude.process.diagnosed`
// carrying the recommended_action ∈ {retry, wait, manual}. On a
// "wait" recommendation the lead instance stays in stale; on
// timeout / parse failure the supervisor falls back to leaving the
// stale envelope as the user's final signal.
package claude

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os/exec"
	"strconv"
	"strings"
	"time"

	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/protocol"
	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/telemetry"
)

// DiagnosticResult captures the parsed outcome of a diagnostic spawn.
// Exposed (capitalised fields) so the test suite can assert per-field
// expectations without poking at the internal envelope path.
type DiagnosticResult struct {
	DiagnosisText        string
	RecommendedAction    string
	DiagnosticTokensUsed int
	DiagnosticDurationMs int64
}

// diagnosticPromptTemplate is the hard-coded English prompt template
// per Q7 of the spec (locked default). Operators wanting Turkish
// localisation can patch this in a follow-up — the template lives in a
// single constant for that reason.
const diagnosticPromptTemplate = "You are a debugging assistant. A long-running `claude -p` " +
	"subprocess (session=%s, pid=%d) has gone silent for %dms. " +
	"Stderr tail (last 8 KiB):\n\n%s\n\n" +
	"Briefly explain (≤200 tokens) what most likely caused the hang " +
	"and recommend ONE of these actions on the LAST line by itself, " +
	"prefixed with 'RECOMMENDATION: '. Allowed actions: " +
	"retry (transient — safe to re-run), wait (rate-limit / backend " +
	"throttle — re-run later), manual (operator must intervene)."

// runDiagnostic is the supervisor-internal entry point. It honours
// the depth guard, builds the diagnostic prompt, runs the spawn with
// a per-spawn timeout, parses the result and fires the
// event.claude.process.diagnosed envelope.
//
// Caller (probeLoop) has already verified self-heal preconditions
// (rate-limit cache miss, SelfHealEnabled, non-orphan).
func (s *Supervisor) runDiagnostic(inst *instance) {
	if !s.diagnosticDepth.CompareAndSwap(0, 1) {
		// Another diagnostic is in flight. Hard depth cap per spec
		// §8 — increment the per-outcome counter and bail out so the
		// stale envelope remains the user's signal.
		telemetry.ClaudeSupervisorSelfHealsTotal.Add(supervisorSelfHealOutcomeCapped, 1)
		return
	}
	defer s.diagnosticDepth.Store(0)

	if s.cfg.MaxDiagnosticDepth <= 0 {
		// Operator opted out via config (depth = 0 means "no
		// recursion AND no top-level spawn either" so the operator
		// can disable diagnostics without flipping the whole
		// feature flag).
		telemetry.ClaudeSupervisorSelfHealsTotal.Add(supervisorSelfHealOutcomeCapped, 1)
		return
	}

	telemetry.ClaudeSupervisorDiagnosticsTotal.Add(1)

	// Snapshot under lock so the goroutine's later reads do not race
	// with concurrent Touch / Unregister.
	s.mu.Lock()
	live, ok := s.instances[inst.sessionID]
	if ok && live.gen == inst.gen {
		s.transitionLocked(live, StateDiagnosing, s.clock.Now())
	}
	sessionID := inst.sessionID
	pid := inst.pid
	stderrTail, _ := inst.stderrRing.Tail()
	maxTokens := s.cfg.DiagnosticMaxTokens
	timeout := s.cfg.DiagnosticTimeout
	binary := s.diagnosticBinary
	execFn := s.diagnosticExec
	now := s.clock.Now()
	staleForMs := int64(0)
	if !inst.lastStdoutAt.IsZero() {
		staleForMs = now.Sub(inst.lastStdoutAt).Milliseconds()
	}
	sink := s.sink
	s.mu.Unlock()

	prompt := fmt.Sprintf(diagnosticPromptTemplate, sessionID, pid, staleForMs, capStderrTailForPrompt(stderrTail))

	ctx, cancel := context.WithTimeout(s.ctx, timeout)
	defer cancel()

	args := []string{
		"-p",
		"--output-format", "stream-json",
		"--verbose",
		"--max-tokens", strconv.Itoa(maxTokens),
		prompt,
	}

	start := s.clock.Now()
	cmd := execFn(ctx, binary, args...)
	out, runErr := cmd.Output()
	durMs := s.clock.Now().Sub(start).Milliseconds()

	if runErr != nil && !errors.Is(ctx.Err(), context.DeadlineExceeded) {
		// Spawn itself failed — increment the failed counter and
		// leave the lead instance in stale.
		telemetry.ClaudeSupervisorSelfHealsTotal.Add(supervisorSelfHealOutcomeFailed, 1)
		s.logger.Warn("supervisor: diagnostic spawn failed",
			"err", runErr,
			"session_id", sessionID,
			"pid", pid,
		)
		s.revertDiagnosingToStale(sessionID, inst.gen)
		return
	}
	if errors.Is(ctx.Err(), context.DeadlineExceeded) {
		telemetry.ClaudeSupervisorSelfHealsTotal.Add(supervisorSelfHealOutcomeFailed, 1)
		s.logger.Warn("supervisor: diagnostic spawn timed out",
			"timeout", timeout,
			"session_id", sessionID,
		)
		s.revertDiagnosingToStale(sessionID, inst.gen)
		return
	}

	result, parseErr := parseDiagnosticOutput(out)
	if parseErr != nil {
		telemetry.ClaudeSupervisorSelfHealsTotal.Add(supervisorSelfHealOutcomeFailed, 1)
		s.logger.Warn("supervisor: diagnostic output parse failed",
			"err", parseErr,
			"session_id", sessionID,
		)
		s.revertDiagnosingToStale(sessionID, inst.gen)
		return
	}
	result.DiagnosticDurationMs = durMs
	if result.DiagnosticTokensUsed > maxTokens {
		// Defensive — the spawn argv enforces --max-tokens but the
		// CLI may report the soft cap. Clamp for the envelope so the
		// iOS UI never sees a value above the configured ceiling.
		result.DiagnosticTokensUsed = maxTokens
	}
	if len(result.DiagnosisText) > diagnosisTextCap {
		result.DiagnosisText = result.DiagnosisText[:diagnosisTextCap]
	}

	if sink != nil {
		sink.OnDiagnosed(protocol.EventClaudeProcessDiagnosed{
			SessionID:            sessionID,
			DiagnosisText:        result.DiagnosisText,
			RecommendedAction:    result.RecommendedAction,
			DiagnosticTokensUsed: result.DiagnosticTokensUsed,
			DiagnosticDurationMs: result.DiagnosticDurationMs,
			DiagnosedAt:          s.clock.Now().UTC().Format(time.RFC3339Nano),
		})
	}

	// On a "wait" recommendation, transition the lead instance from
	// diagnosing → running so the iOS banner clears (the user gets
	// the recommendation but the supervisor doesn't keep retrying).
	if result.RecommendedAction == "wait" {
		s.applyDiagnosticWait(sessionID, inst.gen)
	} else {
		// retry / manual — leave the lead instance in stale so the
		// iOS user sees the diagnosis-with-action and decides.
		s.revertDiagnosingToStale(sessionID, inst.gen)
	}
}

// capStderrTailForPrompt trims the stderr tail to fit within the
// diagnostic prompt template comfortably. The template ceiling is
// stderrTailCap (8 KiB) — anything larger is unlikely to fit in a
// 500-token diagnosis budget anyway.
func capStderrTailForPrompt(s string) string {
	if len(s) > stderrTailCap {
		return s[len(s)-stderrTailCap:]
	}
	return s
}

// revertDiagnosingToStale flips the instance back to stale on a
// failed / timed-out / non-wait diagnostic so the user-visible
// "stale" banner persists. No envelope is emitted here — the
// stalled envelope already fired before the diagnostic spawned.
func (s *Supervisor) revertDiagnosingToStale(sessionID string, gen uint64) {
	now := s.clock.Now()
	s.mu.Lock()
	defer s.mu.Unlock()
	inst, ok := s.instances[sessionID]
	if !ok || inst.gen != gen {
		return
	}
	if inst.state == StateDiagnosing {
		s.transitionLocked(inst, StateStale, now)
	}
}

// applyDiagnosticWait flips the instance from diagnosing back to
// running with a synthetic recovery envelope. Mirrors the spec §3
// "diagnosing → running on diagnostic_recommended_wait" arrow.
func (s *Supervisor) applyDiagnosticWait(sessionID string, gen uint64) {
	now := s.clock.Now()
	s.mu.Lock()
	inst, ok := s.instances[sessionID]
	if !ok || inst.gen != gen {
		s.mu.Unlock()
		return
	}
	if inst.state == StateDiagnosing {
		s.transitionLocked(inst, StateRunning, now)
	}
	sink := s.sink
	s.mu.Unlock()

	if sink != nil {
		sink.OnRecovered(protocol.EventClaudeProcessRecovered{
			OldSessionID:   sessionID,
			NewSessionID:   sessionID,
			RecoveryReason: RecoveryReasonDiagnosticWait,
			RecoveredAt:    now.UTC().Format(time.RFC3339Nano),
		})
		telemetry.ClaudeSupervisorSelfHealsTotal.Add(supervisorSelfHealOutcomeRecovery, 1)
	}
}

// parseDiagnosticOutput reads the diagnostic claude's stream-json
// output and extracts (DiagnosisText, RecommendedAction,
// DiagnosticTokensUsed). Tolerates either a final "result" frame
// carrying the full text, or an explicit JSON object on stdout that
// already contains the three canonical fields (used by the test
// suite's fake claude binary).
func parseDiagnosticOutput(out []byte) (DiagnosticResult, error) {
	trimmed := strings.TrimSpace(string(out))
	if trimmed == "" {
		return DiagnosticResult{}, errors.New("diagnostic: empty output")
	}

	// Fast path — the test fake emits a single JSON object that
	// matches the DiagnosticResult shape exactly. Try this first so
	// tests don't have to fabricate stream-json frames.
	var direct struct {
		DiagnosisText        string `json:"diagnosis_text"`
		RecommendedAction    string `json:"recommended_action"`
		DiagnosticTokensUsed int    `json:"diagnostic_tokens_used"`
	}
	if err := json.Unmarshal([]byte(trimmed), &direct); err == nil && direct.DiagnosisText != "" {
		return DiagnosticResult{
			DiagnosisText:        direct.DiagnosisText,
			RecommendedAction:    canonicalAction(direct.RecommendedAction),
			DiagnosticTokensUsed: direct.DiagnosticTokensUsed,
		}, nil
	}

	// Slow path — stream-json. Walk every line, accumulate any
	// assistant text/content fields and read tokens off the result
	// frame.
	var (
		text   strings.Builder
		tokens int
	)
	scanner := bufio.NewScanner(strings.NewReader(trimmed))
	scanner.Buffer(make([]byte, 64*1024), 4*1024*1024)
	for scanner.Scan() {
		line := scanner.Bytes()
		var head struct {
			Type    string          `json:"type"`
			Subtype string          `json:"subtype,omitempty"`
			Message json.RawMessage `json:"message,omitempty"`
		}
		if err := json.Unmarshal(line, &head); err != nil {
			continue
		}
		switch head.Type {
		case "assistant":
			extractAssistantText(head.Message, &text)
		case "result":
			var res struct {
				Result string `json:"result"`
				Usage  struct {
					InputTokens  int `json:"input_tokens"`
					OutputTokens int `json:"output_tokens"`
				} `json:"usage"`
				ModelUsage map[string]struct {
					InputTokens  int `json:"input_tokens"`
					OutputTokens int `json:"output_tokens"`
				} `json:"model_usage"`
			}
			if err := json.Unmarshal(line, &res); err == nil {
				if res.Result != "" {
					text.WriteString(res.Result)
				}
				if res.Usage.OutputTokens > 0 {
					tokens = res.Usage.OutputTokens
				}
				for _, mu := range res.ModelUsage {
					tokens += mu.OutputTokens
				}
			}
		}
	}
	body := strings.TrimSpace(text.String())
	if body == "" {
		return DiagnosticResult{}, errors.New("diagnostic: no text recovered from stream-json")
	}
	action := extractRecommendation(body)
	return DiagnosticResult{
		DiagnosisText:        body,
		RecommendedAction:    canonicalAction(action),
		DiagnosticTokensUsed: tokens,
	}, nil
}

// extractAssistantText pulls out the concatenated `text` fields from
// a claude assistant message envelope. Robust to either the
// content-array shape (claude CLI) or a top-level text field.
func extractAssistantText(msg json.RawMessage, w *strings.Builder) {
	if len(msg) == 0 {
		return
	}
	var shape struct {
		Content []struct {
			Type string `json:"type"`
			Text string `json:"text"`
		} `json:"content"`
		Text string `json:"text"`
	}
	if err := json.Unmarshal(msg, &shape); err != nil {
		return
	}
	if shape.Text != "" {
		w.WriteString(shape.Text)
	}
	for _, c := range shape.Content {
		if c.Type == "text" || c.Type == "" {
			w.WriteString(c.Text)
		}
	}
}

// extractRecommendation walks the diagnosis text from the bottom up
// looking for the canonical "RECOMMENDATION: <action>" trailer.
func extractRecommendation(text string) string {
	lines := strings.Split(text, "\n")
	for i := len(lines) - 1; i >= 0; i-- {
		line := strings.TrimSpace(lines[i])
		if strings.HasPrefix(strings.ToUpper(line), "RECOMMENDATION:") {
			return strings.TrimSpace(line[len("RECOMMENDATION:"):])
		}
	}
	return ""
}

// canonicalAction normalises operator-recommended action labels to
// the closed envelope set {retry, wait, manual}. Anything we don't
// recognise falls back to "manual" so the iOS UI always shows a
// definite action.
func canonicalAction(s string) string {
	switch strings.ToLower(strings.TrimSpace(s)) {
	case "retry":
		return "retry"
	case "wait":
		return "wait"
	case "manual":
		return "manual"
	default:
		return "manual"
	}
}

// silenceUnusedExecImport keeps "os/exec" referenced after a
// future refactor that might temporarily move the diagnostic
// invocation out of this file. Cheap enough to leave in place; the
// Go compiler eliminates the reference at zero runtime cost.
var _ = exec.CommandContext
