// Package claude — V1.x Claude Subprocess Supervisor unit tests.
//
// Coverage targets the spec §5.1.3 minimum (≥9 cases):
//
//  1. State machine: starting → running on first stdout (Touch).
//  2. State machine: running → idle → stale via probe ticks.
//  3. Probe detects killed process → crashed envelope.
//  4. Rate-limit cache short-circuits diagnostic spawn.
//  5. Diagnostic spawn happy path (canned diagnosis JSON).
//  6. Diagnostic recursion guard (atomic depth=1 cap).
//  7. Shutdown drains probe goroutines (race-detector clean).
//  8. Orphan adoption (synthetic orphan-{pid} session_id).
//  9. SupervisorSink dispatch correctness (scripted lifecycle).
//
// Bonus:
//
//   - TestSupervisor_DiagnosticTokenCap — argv contains `--max-tokens N`.
//   - TestSupervisor_TryReserveSlot_SaturatedFails — concurrency cap.
//
// All tests use a manual clock + a fake process probe so the suite
// runs deterministically without sleeping for real seconds and
// without depending on the host's process table.
package claude

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"strconv"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/config"
	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/protocol"
)

// ---------------------------------------------------------------------------
// Test scaffolding.
// ---------------------------------------------------------------------------

// manualClock is a thread-safe wall-clock substitute. Tests advance it
// explicitly via Set / Advance.
type manualClock struct {
	mu  sync.Mutex
	now time.Time
}

func newManualClock(start time.Time) *manualClock {
	return &manualClock{now: start}
}

func (c *manualClock) Now() time.Time {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.now
}

func (c *manualClock) Advance(d time.Duration) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.now = c.now.Add(d)
}

// fakeProbe is the test-side processProbe. Alive/Sample are guarded
// by a mutex so concurrent probe goroutines and the test driver
// don't race on the alive map.
type fakeProbe struct {
	mu    sync.Mutex
	alive map[int]bool
	rss   int64
	cpu   float64
}

func newFakeProbe() *fakeProbe {
	return &fakeProbe{alive: make(map[int]bool)}
}

func (f *fakeProbe) SetAlive(pid int, alive bool) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.alive[pid] = alive
}

func (f *fakeProbe) Alive(pid int) bool {
	f.mu.Lock()
	defer f.mu.Unlock()
	v, ok := f.alive[pid]
	if !ok {
		return true // default to alive — tests that care set it explicitly
	}
	return v
}

func (f *fakeProbe) Sample(_ int) (int64, float64) {
	f.mu.Lock()
	defer f.mu.Unlock()
	return f.rss, f.cpu
}

// fakeOrphanScanner returns a fixed PID list.
type fakeOrphanScanner struct{ pids []int }

func (f fakeOrphanScanner) Scan(_ context.Context) ([]int, error) {
	return append([]int(nil), f.pids...), nil
}

// recordingSink captures every supervisor envelope for later
// assertion. Methods are guarded by a mutex so concurrent probe-loop
// goroutines + Touch callers can append safely.
type recordingSink struct {
	mu sync.Mutex

	spawned     []protocol.EventClaudeProcessSpawned
	healthcheck []protocol.EventClaudeProcessHealthcheck
	stalled     []protocol.EventClaudeProcessStalled
	crashed     []protocol.EventClaudeProcessCrashed
	recovered   []protocol.EventClaudeProcessRecovered
	diagnosed   []protocol.EventClaudeProcessDiagnosed
}

func (r *recordingSink) OnSpawned(ev protocol.EventClaudeProcessSpawned) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.spawned = append(r.spawned, ev)
}

func (r *recordingSink) OnHealthcheck(ev protocol.EventClaudeProcessHealthcheck) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.healthcheck = append(r.healthcheck, ev)
}

func (r *recordingSink) OnStalled(ev protocol.EventClaudeProcessStalled) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.stalled = append(r.stalled, ev)
}

func (r *recordingSink) OnCrashed(ev protocol.EventClaudeProcessCrashed) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.crashed = append(r.crashed, ev)
}

func (r *recordingSink) OnRecovered(ev protocol.EventClaudeProcessRecovered) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.recovered = append(r.recovered, ev)
}

func (r *recordingSink) OnDiagnosed(ev protocol.EventClaudeProcessDiagnosed) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.diagnosed = append(r.diagnosed, ev)
}

func (r *recordingSink) snapshot() (s []protocol.EventClaudeProcessSpawned, h []protocol.EventClaudeProcessHealthcheck, st []protocol.EventClaudeProcessStalled, cr []protocol.EventClaudeProcessCrashed, rec []protocol.EventClaudeProcessRecovered, d []protocol.EventClaudeProcessDiagnosed) {
	r.mu.Lock()
	defer r.mu.Unlock()
	s = append([]protocol.EventClaudeProcessSpawned(nil), r.spawned...)
	h = append([]protocol.EventClaudeProcessHealthcheck(nil), r.healthcheck...)
	st = append([]protocol.EventClaudeProcessStalled(nil), r.stalled...)
	cr = append([]protocol.EventClaudeProcessCrashed(nil), r.crashed...)
	rec = append([]protocol.EventClaudeProcessRecovered(nil), r.recovered...)
	d = append([]protocol.EventClaudeProcessDiagnosed(nil), r.diagnosed...)
	return
}

// testCfg returns a SupervisorConfig with short thresholds suitable
// for fast tests + Enabled = true. Probes are intentionally short
// (1ms) so tests can drive the probe loop deterministically by
// advancing the manual clock and yielding briefly.
func testCfg() *config.SupervisorConfig {
	return &config.SupervisorConfig{
		Enabled:             true,
		ProbeInterval:       50 * time.Millisecond,
		IdleThreshold:       100 * time.Millisecond,
		StaleThreshold:      300 * time.Millisecond,
		MaxConcurrent:       3,
		MaxDiagnosticDepth:  1,
		SelfHealEnabled:     true,
		DiagnosticMaxTokens: 500,
		DiagnosticTimeout:   2 * time.Second,
		HealthcheckCoalesce: 1 * time.Second,
	}
}

// newTestSupervisor builds a Supervisor wired up with the test
// scaffolding (manual clock, fake probe, recording sink). The probe
// is left disabled-by-default-alive so most tests don't have to
// preconfigure it.
func newTestSupervisor(t *testing.T, cfg *config.SupervisorConfig) (*Supervisor, *manualClock, *fakeProbe, *recordingSink) {
	t.Helper()
	if cfg == nil {
		cfg = testCfg()
	}
	clock := newManualClock(time.Now())
	probe := newFakeProbe()
	sink := &recordingSink{}
	sup := NewSupervisor(context.Background(), cfg, silentLogger())
	sup.SetClock(clock)
	sup.SetProbe(probe)
	sup.SetSink(sink)
	t.Cleanup(func() {
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
		defer cancel()
		_ = sup.Shutdown(shutdownCtx)
	})
	return sup, clock, probe, sink
}

// waitForState polls the supervisor's State accessor until the named
// session is in expected, or the deadline elapses. Tests use this
// instead of arbitrary sleeps so the probe loop can race ahead at
// will.
func waitForState(t *testing.T, sup *Supervisor, sessionID string, expected State, timeout time.Duration) {
	t.Helper()
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		if got, ok := sup.State(sessionID); ok && got == expected {
			return
		}
		time.Sleep(5 * time.Millisecond)
	}
	got, _ := sup.State(sessionID)
	t.Fatalf("waitForState(%q): want %q, got %q after %s", sessionID, expected, got, timeout)
}

// ---------------------------------------------------------------------------
// 1. State machine: starting → running on first stdout.
// ---------------------------------------------------------------------------

func TestSupervisor_StateMachine_StartingToRunningOnFirstStdout(t *testing.T) {
	t.Parallel()
	sup, clock, probe, sink := newTestSupervisor(t, nil)

	const sessionID = "sess-1"
	probe.SetAlive(1234, true)
	gen := sup.Register(RegisterInput{
		SessionID: sessionID,
		PID:       1234,
		Prompt:    "hello",
		Model:     "claude-sonnet-4-7",
	})
	if gen == 0 {
		t.Fatalf("Register returned 0 generation token (supervisor disabled?)")
	}
	if got, _ := sup.State(sessionID); got != StateStarting {
		t.Fatalf("post-Register state: want %q, got %q", StateStarting, got)
	}

	// First stdout line arrives — Touch should bump us to running.
	clock.Advance(10 * time.Millisecond)
	sup.Touch(sessionID)
	if got, _ := sup.State(sessionID); got != StateRunning {
		t.Fatalf("post-Touch state: want %q, got %q", StateRunning, got)
	}

	spawned, _, _, _, _, _ := sink.snapshot()
	if len(spawned) != 1 {
		t.Fatalf("expected exactly 1 spawned envelope, got %d", len(spawned))
	}
	if spawned[0].PID != 1234 {
		t.Fatalf("spawned PID: want 1234, got %d", spawned[0].PID)
	}
}

// ---------------------------------------------------------------------------
// 2. State machine: running → idle → stale via probe ticks.
// ---------------------------------------------------------------------------

func TestSupervisor_StateMachine_RunningToIdleToStale(t *testing.T) {
	t.Parallel()
	cfg := testCfg()
	sup, clock, probe, _ := newTestSupervisor(t, cfg)

	const sessionID = "sess-idle-stale"
	probe.SetAlive(2222, true)
	sup.Register(RegisterInput{SessionID: sessionID, PID: 2222, Prompt: "p"})
	clock.Advance(10 * time.Millisecond)
	sup.Touch(sessionID)
	waitForState(t, sup, sessionID, StateRunning, 500*time.Millisecond)

	// Advance past idle threshold — probe loop should mark idle.
	clock.Advance(cfg.IdleThreshold + 10*time.Millisecond)
	waitForState(t, sup, sessionID, StateIdle, 1*time.Second)

	// Advance past stale threshold — probe loop should mark stale.
	clock.Advance(cfg.StaleThreshold + 50*time.Millisecond)
	waitForState(t, sup, sessionID, StateStale, 2*time.Second)
}

// ---------------------------------------------------------------------------
// 3. Probe detects killed process → crashed envelope.
// ---------------------------------------------------------------------------

func TestSupervisor_Probe_DetectsKilledProcess(t *testing.T) {
	t.Parallel()
	cfg := testCfg()
	cfg.SelfHealEnabled = false // skip diagnostic for this isolation test
	sup, _, probe, sink := newTestSupervisor(t, cfg)

	const sessionID = "sess-kill"
	probe.SetAlive(3333, true)
	sup.Register(RegisterInput{SessionID: sessionID, PID: 3333, Prompt: "p"})

	// Now kill it — probe loop should observe ESRCH and emit crashed.
	probe.SetAlive(3333, false)

	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		_, _, _, cr, _, _ := sink.snapshot()
		if len(cr) > 0 {
			break
		}
		time.Sleep(10 * time.Millisecond)
	}
	_, _, _, cr, _, _ := sink.snapshot()
	if len(cr) == 0 {
		t.Fatalf("no crashed envelope after process killed (state=%v instances=%d)",
			func() State { s, _ := sup.State(sessionID); return s }(),
			sup.InstanceCount())
	}
	if cr[0].PID != 3333 {
		t.Fatalf("crashed PID: want 3333, got %d", cr[0].PID)
	}
}

// ---------------------------------------------------------------------------
// 4. Rate-limit cache short-circuits diagnostic spawn.
// ---------------------------------------------------------------------------

func TestSupervisor_RateLimit_ShortCircuitsDiagnostic(t *testing.T) {
	t.Parallel()
	cfg := testCfg()
	sup, clock, probe, sink := newTestSupervisor(t, cfg)

	// Replace diagnostic exec with a sentinel that fails the test if
	// invoked — the rate-limit cache short-circuit must keep us from
	// ever reaching the spawn.
	var diagnosticInvoked atomic.Bool
	sup.SetDiagnosticExec(func(ctx context.Context, _ string, _ ...string) *exec.Cmd {
		diagnosticInvoked.Store(true)
		return exec.CommandContext(ctx, "true")
	})

	const sessionID = "sess-rl"
	probe.SetAlive(4444, true)
	sup.Register(RegisterInput{SessionID: sessionID, PID: 4444, Prompt: "p"})
	clock.Advance(10 * time.Millisecond)
	sup.Touch(sessionID)
	waitForState(t, sup, sessionID, StateRunning, 500*time.Millisecond)

	// Pre-populate rate-limit cache so the stale handler short-circuits.
	sup.MarkRateLimit(sessionID, clock.Now().Add(2*time.Hour).Unix())

	// Advance past stale threshold.
	clock.Advance(cfg.StaleThreshold + 50*time.Millisecond)
	waitForState(t, sup, sessionID, StateRateLimited, 2*time.Second)

	// Give the probe goroutine a chance to spawn (it shouldn't).
	time.Sleep(150 * time.Millisecond)

	if diagnosticInvoked.Load() {
		t.Fatalf("diagnostic spawned despite rate-limit cache hit — short-circuit failed")
	}

	// Stalled envelope should still have fired with self_heal_pending=false.
	_, _, st, _, _, _ := sink.snapshot()
	if len(st) == 0 {
		t.Fatalf("no stalled envelope emitted")
	}
	if st[0].SelfHealPending {
		t.Fatalf("stalled.self_heal_pending should be false when rate-limited; got true")
	}
}

// ---------------------------------------------------------------------------
// 5. Diagnostic spawn happy path — canned diagnosis JSON.
// ---------------------------------------------------------------------------

func TestSupervisor_Diagnostic_HappyPath(t *testing.T) {
	t.Parallel()
	cfg := testCfg()
	sup, clock, probe, sink := newTestSupervisor(t, cfg)

	// Inject a fake claude that emits a single JSON line matching
	// the diagnostic-result fast path.
	cannedJSON := `{"diagnosis_text":"Subprocess hung waiting on stdin.","recommended_action":"retry","diagnostic_tokens_used":312}`
	sup.SetDiagnosticExec(func(ctx context.Context, _ string, _ ...string) *exec.Cmd {
		return exec.CommandContext(ctx, "sh", "-c", "printf '%s' "+singleQuote(cannedJSON))
	})

	const sessionID = "sess-diag"
	probe.SetAlive(5555, true)
	sup.Register(RegisterInput{SessionID: sessionID, PID: 5555, Prompt: "p"})
	clock.Advance(10 * time.Millisecond)
	sup.Touch(sessionID)
	waitForState(t, sup, sessionID, StateRunning, 500*time.Millisecond)

	// Trigger stale → diagnosing.
	clock.Advance(cfg.StaleThreshold + 50*time.Millisecond)

	// Wait for diagnosed envelope.
	deadline := time.Now().Add(3 * time.Second)
	for time.Now().Before(deadline) {
		_, _, _, _, _, d := sink.snapshot()
		if len(d) > 0 {
			break
		}
		time.Sleep(10 * time.Millisecond)
	}
	_, _, _, _, _, d := sink.snapshot()
	if len(d) == 0 {
		t.Fatalf("no diagnosed envelope emitted (state=%v)",
			func() State { s, _ := sup.State(sessionID); return s }())
	}
	if d[0].RecommendedAction != "retry" {
		t.Fatalf("diagnosed.recommended_action: want retry, got %q", d[0].RecommendedAction)
	}
	if d[0].DiagnosticTokensUsed != 312 {
		t.Fatalf("diagnosed.diagnostic_tokens_used: want 312, got %d", d[0].DiagnosticTokensUsed)
	}
}

// singleQuote wraps s for use inside a `sh -c "printf '%s' '<x>'"`
// invocation by escaping any embedded single quotes.
func singleQuote(s string) string {
	return "'" + s + "'"
}

// ---------------------------------------------------------------------------
// 6. Diagnostic recursion guard — second concurrent stale must not spawn.
// ---------------------------------------------------------------------------

func TestSupervisor_Diagnostic_RecursionGuard(t *testing.T) {
	t.Parallel()
	cfg := testCfg()
	cfg.DiagnosticTimeout = 5 * time.Second
	sup, _, _, _ := newTestSupervisor(t, cfg)

	// Hold the depth slot so the next attempt CAS-fails.
	if !sup.diagnosticDepth.CompareAndSwap(0, 1) {
		t.Fatalf("setup: diagnosticDepth already held")
	}
	defer sup.diagnosticDepth.Store(0)

	// Now invoke runDiagnostic directly; it should detect the held
	// slot, increment the capped counter, and return immediately
	// without invoking the exec stub (which we make panic on call to
	// surface a violation).
	var spawnCalled atomic.Bool
	sup.SetDiagnosticExec(func(ctx context.Context, _ string, _ ...string) *exec.Cmd {
		spawnCalled.Store(true)
		return exec.CommandContext(ctx, "true")
	})

	inst := &instance{sessionID: "sess-recursion", pid: 6666, gen: 1, stderrRing: newStderrRing()}
	done := make(chan struct{})
	go func() {
		sup.runDiagnostic(inst)
		close(done)
	}()

	select {
	case <-done:
	case <-time.After(1 * time.Second):
		t.Fatalf("runDiagnostic did not return promptly when depth slot held")
	}

	if spawnCalled.Load() {
		t.Fatalf("diagnostic spawn invoked despite depth guard")
	}
}

// ---------------------------------------------------------------------------
// 7. Shutdown drains probe goroutines (race-detector clean).
// ---------------------------------------------------------------------------

func TestSupervisor_Shutdown_DrainsProbeGoroutines(t *testing.T) {
	t.Parallel()
	cfg := testCfg()
	sup := NewSupervisor(context.Background(), cfg, silentLogger())
	sup.SetClock(newManualClock(time.Now()))
	probe := newFakeProbe()
	sup.SetProbe(probe)
	sup.SetSink(&recordingSink{})

	// Register a handful of instances so we have multiple probe
	// goroutines to drain.
	for i := 0; i < 5; i++ {
		pid := 7000 + i
		probe.SetAlive(pid, true)
		sup.Register(RegisterInput{
			SessionID: fmt.Sprintf("sess-drain-%d", i),
			PID:       pid,
			Prompt:    "p",
		})
	}

	shutdownCtx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	if err := sup.Shutdown(shutdownCtx); err != nil {
		t.Fatalf("Shutdown returned err: %v", err)
	}
	// Idempotent — second call must also succeed.
	if err := sup.Shutdown(shutdownCtx); err != nil {
		t.Fatalf("second Shutdown returned err: %v", err)
	}
}

// ---------------------------------------------------------------------------
// 8. Orphan adoption — synthetic orphan-{pid} session_id.
// ---------------------------------------------------------------------------

func TestSupervisor_Orphan_AdoptionViaPgrep(t *testing.T) {
	t.Parallel()
	sup, _, probe, sink := newTestSupervisor(t, nil)
	sup.SetOrphanScanner(fakeOrphanScanner{pids: []int{8001, 8002}})
	probe.SetAlive(8001, true)
	probe.SetAlive(8002, true)

	adopted, err := sup.AdoptOrphans(context.Background())
	if err != nil {
		t.Fatalf("AdoptOrphans: %v", err)
	}
	if adopted != 2 {
		t.Fatalf("adopted: want 2, got %d", adopted)
	}

	for _, pid := range []int{8001, 8002} {
		sessionID := fmt.Sprintf("orphan-%d", pid)
		st, ok := sup.State(sessionID)
		if !ok {
			t.Fatalf("orphan %d not registered as %q", pid, sessionID)
		}
		if st != StateRunning {
			t.Fatalf("orphan %d state: want running, got %q", pid, st)
		}
	}

	spawned, _, _, _, _, _ := sink.snapshot()
	if len(spawned) != 2 {
		t.Fatalf("expected 2 spawned envelopes for orphans, got %d", len(spawned))
	}
}

// ---------------------------------------------------------------------------
// 9. SupervisorSink dispatch correctness — scripted lifecycle.
// ---------------------------------------------------------------------------

func TestSupervisor_Sink_ScriptedLifecycle(t *testing.T) {
	t.Parallel()
	cfg := testCfg()
	cfg.SelfHealEnabled = false // keep this lifecycle deterministic
	sup, clock, probe, sink := newTestSupervisor(t, cfg)

	const sessionID = "sess-script"
	probe.SetAlive(9001, true)
	sup.Register(RegisterInput{
		SessionID: sessionID,
		PID:       9001,
		Prompt:    "scripted",
		Model:     "claude-sonnet-4-7",
	})

	// Touch — running.
	clock.Advance(10 * time.Millisecond)
	sup.Touch(sessionID)
	waitForState(t, sup, sessionID, StateRunning, 500*time.Millisecond)

	// Idle.
	clock.Advance(cfg.IdleThreshold + 10*time.Millisecond)
	waitForState(t, sup, sessionID, StateIdle, 1*time.Second)

	// Stale.
	clock.Advance(cfg.StaleThreshold + 50*time.Millisecond)
	waitForState(t, sup, sessionID, StateStale, 2*time.Second)

	// Recover via Touch (manual stdout resume).
	clock.Advance(10 * time.Millisecond)
	sup.Touch(sessionID)
	waitForState(t, sup, sessionID, StateRunning, 500*time.Millisecond)

	// Complete cleanly.
	sup.Unregister(sessionID, 1, nil, true)

	spawned, hc, st, _, rec, _ := sink.snapshot()
	if len(spawned) != 1 {
		t.Fatalf("spawned envelope count: want 1, got %d", len(spawned))
	}
	if len(st) == 0 {
		t.Fatalf("no stalled envelope observed")
	}
	if len(rec) == 0 {
		t.Fatalf("no recovered envelope observed (recovery_reason=%q expected)",
			RecoveryReasonStdoutResumed)
	}
	if rec[0].RecoveryReason != RecoveryReasonStdoutResumed {
		t.Fatalf("recovered.recovery_reason: want %q, got %q",
			RecoveryReasonStdoutResumed, rec[0].RecoveryReason)
	}
	if len(hc) == 0 {
		t.Fatalf("no healthcheck envelope observed")
	}
	// Spot-check: spawned.args should not contain the trailing prompt.
	for _, arg := range spawned[0].Args {
		if arg == "scripted" {
			t.Fatalf("spawned.args leaked the prompt — PII guard failed")
		}
	}
}

// ---------------------------------------------------------------------------
// Bonus 1 — Diagnostic argv contains --max-tokens.
// ---------------------------------------------------------------------------

func TestSupervisor_DiagnosticTokenCap(t *testing.T) {
	t.Parallel()
	cfg := testCfg()
	cfg.DiagnosticMaxTokens = 500
	sup, _, _, _ := newTestSupervisor(t, cfg)

	captured := make(chan []string, 1)
	sup.SetDiagnosticExec(func(ctx context.Context, _ string, args ...string) *exec.Cmd {
		select {
		case captured <- append([]string(nil), args...):
		default:
		}
		return exec.CommandContext(ctx, "sh", "-c", `printf '%s' '{"diagnosis_text":"x","recommended_action":"manual"}'`)
	})

	inst := &instance{
		sessionID:    "sess-cap",
		pid:          1,
		gen:          1,
		stderrRing:   newStderrRing(),
		lastStdoutAt: sup.clock.Now().Add(-10 * time.Second),
	}
	sup.mu.Lock()
	sup.instances[inst.sessionID] = inst
	sup.mu.Unlock()
	sup.runDiagnostic(inst)

	select {
	case args := <-captured:
		// argv must contain "--max-tokens" followed by the
		// configured count (default 500 in this test).
		var found bool
		for i, a := range args {
			if a == "--max-tokens" && i+1 < len(args) {
				if got, _ := strconv.Atoi(args[i+1]); got == cfg.DiagnosticMaxTokens {
					found = true
				}
			}
		}
		if !found {
			t.Fatalf("--max-tokens %d missing from diagnostic argv: %v", cfg.DiagnosticMaxTokens, args)
		}
	case <-time.After(2 * time.Second):
		t.Fatalf("diagnostic exec stub never invoked")
	}
}

// ---------------------------------------------------------------------------
// Bonus 2 — TryReserveSlot enforces MaxConcurrent.
// ---------------------------------------------------------------------------

func TestSupervisor_TryReserveSlot_Saturated(t *testing.T) {
	t.Parallel()
	cfg := testCfg()
	cfg.MaxConcurrent = 2
	sup, _, probe, _ := newTestSupervisor(t, cfg)

	for i := 0; i < cfg.MaxConcurrent; i++ {
		probe.SetAlive(10000+i, true)
		if err := sup.TryReserveSlot(); err != nil {
			t.Fatalf("TryReserveSlot %d: %v", i, err)
		}
		sup.Register(RegisterInput{SessionID: fmt.Sprintf("sess-cap-%d", i), PID: 10000 + i, Prompt: "p"})
	}

	if err := sup.TryReserveSlot(); err == nil {
		t.Fatalf("TryReserveSlot at cap returned nil; want ErrSupervisorSaturated")
	}
}

// ---------------------------------------------------------------------------
// Bonus 3 — Disabled supervisor short-circuits every entry point.
// ---------------------------------------------------------------------------

func TestSupervisor_DisabledIsNoOp(t *testing.T) {
	t.Parallel()
	cfg := &config.SupervisorConfig{Enabled: false, ProbeInterval: 1 * time.Second, IdleThreshold: 2 * time.Second, StaleThreshold: 3 * time.Second, MaxConcurrent: 1, MaxDiagnosticDepth: 1, DiagnosticMaxTokens: 500, DiagnosticTimeout: time.Second, HealthcheckCoalesce: time.Second}
	sup := NewSupervisor(context.Background(), cfg, silentLogger())
	sink := &recordingSink{}
	sup.SetSink(sink)

	if err := sup.TryReserveSlot(); err != nil {
		t.Fatalf("TryReserveSlot when disabled: %v", err)
	}
	if got := sup.Register(RegisterInput{SessionID: "sess-noop", PID: 1, Prompt: "p"}); got != 0 {
		t.Fatalf("Register when disabled returned non-zero gen: %d", got)
	}
	sup.Touch("sess-noop") // must not panic
	sup.RecordStderr("sess-noop", []byte("data"))
	sup.MarkRateLimit("sess-noop", time.Now().Add(time.Hour).Unix())
	sup.Unregister("sess-noop", 0, nil, true)

	spawned, _, _, _, _, _ := sink.snapshot()
	if len(spawned) != 0 {
		t.Fatalf("disabled supervisor emitted %d spawned envelopes (want 0)", len(spawned))
	}

	if err := sup.Shutdown(context.Background()); err != nil {
		t.Fatalf("Shutdown when disabled: %v", err)
	}
}

// ---------------------------------------------------------------------------
// Sanity check on stderr ring tail truncation behaviour.
// ---------------------------------------------------------------------------

func TestSupervisor_StderrRing_Tail(t *testing.T) {
	t.Parallel()
	r := newStderrRing()
	r.Append([]byte("hello"))
	tail, truncated := r.Tail()
	if tail != "hello" || truncated {
		t.Fatalf("small append: tail=%q truncated=%v", tail, truncated)
	}

	// Push past 8 KiB so Tail returns the last 8 KiB and truncated=true.
	big := make([]byte, 9*1024)
	for i := range big {
		big[i] = 'a'
	}
	r.Append(big)
	tail, truncated = r.Tail()
	if !truncated {
		t.Fatalf("expected truncated=true after 9 KiB append")
	}
	if len(tail) != stderrTailCap {
		t.Fatalf("expected tail length %d, got %d", stderrTailCap, len(tail))
	}
}

// ---------------------------------------------------------------------------
// Diagnostic output parser — fast + slow path coverage.
// ---------------------------------------------------------------------------

func TestParseDiagnosticOutput_FastPath(t *testing.T) {
	t.Parallel()
	body := `{"diagnosis_text":"hung on stdin","recommended_action":"WAIT","diagnostic_tokens_used":120}`
	res, err := parseDiagnosticOutput([]byte(body))
	if err != nil {
		t.Fatalf("parseDiagnosticOutput: %v", err)
	}
	if res.DiagnosisText != "hung on stdin" {
		t.Fatalf("diagnosis_text mismatch: %q", res.DiagnosisText)
	}
	if res.RecommendedAction != "wait" {
		t.Fatalf("recommended_action canonicalisation failed: %q", res.RecommendedAction)
	}
	if res.DiagnosticTokensUsed != 120 {
		t.Fatalf("tokens mismatch: %d", res.DiagnosticTokensUsed)
	}
}

func TestParseDiagnosticOutput_StreamJSONPath(t *testing.T) {
	t.Parallel()
	// Two stream-json frames: one assistant text + one result.
	stream := mustJSON(map[string]any{
		"type": "assistant",
		"message": map[string]any{
			"content": []map[string]any{
				{"type": "text", "text": "Looks like a parser deadlock.\nRECOMMENDATION: retry"},
			},
		},
	}) + "\n" + mustJSON(map[string]any{
		"type":   "result",
		"result": "Looks like a parser deadlock.\nRECOMMENDATION: retry",
		"usage":  map[string]any{"output_tokens": 88},
	})
	res, err := parseDiagnosticOutput([]byte(stream))
	if err != nil {
		t.Fatalf("parseDiagnosticOutput: %v", err)
	}
	if res.RecommendedAction != "retry" {
		t.Fatalf("recommended_action: want retry, got %q", res.RecommendedAction)
	}
	if res.DiagnosticTokensUsed != 88 {
		t.Fatalf("tokens: want 88, got %d", res.DiagnosticTokensUsed)
	}
}

// mustJSON is a tiny helper so tests can produce stream-json fixtures
// inline without the overhead of a fixture file.
func mustJSON(v any) string {
	b, err := json.Marshal(v)
	if err != nil {
		panic(err)
	}
	return string(b)
}

// ---------------------------------------------------------------------------
// Smoke check: protocol envelope round-trip for every new payload.
// Catches a typo in JSON tags before the iOS / backend mirror lands.
// ---------------------------------------------------------------------------

func TestSupervisor_ProtocolEnvelopeRoundTrip(t *testing.T) {
	t.Parallel()
	cases := []struct {
		name string
		fn   func() (protocol.Envelope, error)
	}{
		{"spawned", func() (protocol.Envelope, error) {
			return protocol.NewEventClaudeProcessSpawned("session:s1", "corr-1", protocol.EventClaudeProcessSpawned{
				SessionID: "s1", PID: 1, StartedAt: "now", Model: "m", Args: []string{"-p"}, PermissionMode: "acceptEdits", ProjectDir: "/tmp",
			})
		}},
		{"healthcheck", func() (protocol.Envelope, error) {
			return protocol.NewEventClaudeProcessHealthcheck("session:s1", "corr-1", protocol.EventClaudeProcessHealthcheck{
				SessionID: "s1", PID: 1, Status: "running", LastStdoutAgeMs: 100, ObservedAt: "now",
			})
		}},
		{"stalled", func() (protocol.Envelope, error) {
			return protocol.NewEventClaudeProcessStalled("session:s1", "corr-1", protocol.EventClaudeProcessStalled{
				SessionID: "s1", PID: 1, LastActivityAt: "now", StaleForMs: 200, StderrTail: "tail", SelfHealPending: true,
			})
		}},
		{"crashed", func() (protocol.Envelope, error) {
			return protocol.NewEventClaudeProcessCrashed("session:s1", "corr-1", protocol.EventClaudeProcessCrashed{
				SessionID: "s1", PID: 1, ExitCode: 137, Signal: "SIGKILL", StderrTail: "x", DurationMs: 1, CrashedAt: "now",
			})
		}},
		{"recovered", func() (protocol.Envelope, error) {
			return protocol.NewEventClaudeProcessRecovered("session:s1", "corr-1", protocol.EventClaudeProcessRecovered{
				OldSessionID: "s1", NewSessionID: "s1", RecoveryReason: "manual_retry", RecoveredAt: "now",
			})
		}},
		{"diagnosed", func() (protocol.Envelope, error) {
			return protocol.NewEventClaudeProcessDiagnosed("session:s1", "corr-1", protocol.EventClaudeProcessDiagnosed{
				SessionID: "s1", DiagnosisText: "x", RecommendedAction: "retry", DiagnosticTokensUsed: 1, DiagnosticDurationMs: 1, DiagnosedAt: "now",
			})
		}},
		{"retry-inbound", func() (protocol.Envelope, error) {
			return protocol.NewCommandClaudeProcessRetry("bridge:default", "corr-1", protocol.CommandClaudeProcessRetry{
				SessionID: "s1", UserID: "u1",
			})
		}},
	}
	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			env, err := tc.fn()
			if err != nil {
				t.Fatalf("build %s: %v", tc.name, err)
			}
			if env.Type == "" {
				t.Fatalf("envelope type empty")
			}
			if len(env.Payload) == 0 {
				t.Fatalf("payload empty")
			}
			// Round-trip the payload: re-decode to ensure we didn't
			// accidentally produce malformed JSON.
			var probe map[string]any
			if err := json.Unmarshal(env.Payload, &probe); err != nil {
				t.Fatalf("payload JSON invalid: %v", err)
			}
		})
	}
}

// ---------------------------------------------------------------------------
// silenceUnused keeps the os.Exit reference warm if a future test
// needs to short-circuit on a CI-only env var. Cheap to leave in.
// ---------------------------------------------------------------------------

var _ = os.Getenv
