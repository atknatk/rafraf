// Package claude — V1.x Claude Subprocess Supervisor.
//
// The Supervisor wraps every spawned `claude -p` subprocess with a
// per-instance state machine, an active liveness probe, and a
// self-heal arm that fires a depth-bounded diagnostic claude when a
// stale instance is detected. Every state-change of interest is pushed
// out through a SupervisorSink (one method per envelope type) — the
// production sink in cmd/bridge/main.go marshals each call into the
// corresponding event.claude.process.* envelope.
//
// State machine (see shared/feature-specs/V1x-claude-supervisor.md §3):
//
//	starting → running        first stdout byte (Touch) OR system/init
//	running  → idle           stdout-silence > IdleThreshold AND alive
//	idle     → stale          stdout-silence > StaleThreshold AND alive
//	stale    → rate_limited   rate-limit cache hit
//	stale    → diagnosing     rate-limit cache miss AND SelfHealEnabled
//	*        → completed      cmd.Wait() == 0 + EventSessionResult
//	*        → crashed        cmd.Wait() != 0
//
// Concurrency model (per spec §8):
//
//   - Every per-instance state read/write is guarded by Supervisor.mu;
//     probe goroutines snapshot under lock then release before I/O.
//   - Probe goroutines are derived from Supervisor.ctx; Shutdown
//     cancels the parent ctx and waits on a sync.WaitGroup. Race
//     detector tests cover this.
//   - Diagnostic recursion is capped via atomic.Int32 CAS(0, 1).
//   - MaxConcurrent is enforced via TryReserveSlot returning
//     ErrSupervisorSaturated.
//
// What the supervisor does NOT do:
//
//   - It does not touch the V1.3 permission broker. Diagnostic spawns
//     deliberately bypass --settings overlay (no PreToolUse hook).
//   - It does not persist state across bridge restarts. Orphan
//     adoption is a best-effort scan via pgrep.
//   - It is not enabled by default in V1.x — see config.SupervisorConfig
//     and the staged rollout in spec §10.
package claude

import (
	"context"
	"fmt"
	"log/slog"
	"os/exec"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"syscall"
	"time"

	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/config"
	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/protocol"
	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/telemetry"
)

// State is the Supervisor's per-instance state-machine label. The
// string values are stable — they are emitted verbatim on the
// healthcheck envelope's `status` field and on the
// claude_supervisor_instances_total{state=…} Prometheus metric.
type State string

const (
	StateStarting    State = "starting"
	StateRunning     State = "running"
	StateIdle        State = "idle"
	StateStale       State = "stale"
	StateDiagnosing  State = "diagnosing"
	StateRateLimited State = "rate_limited"
	StateCrashed     State = "crashed"
	StateCompleted   State = "completed"
)

// stderrRingCap is the in-memory ring-buffer cap per instance. Last
// stderrTailCap bytes are shipped out on stalled/crashed envelopes.
const (
	stderrRingCap         = 16 * 1024 // 16 KiB
	stderrTailCap         = 8 * 1024  // 8 KiB
	diagnosisTextCap      = 4 * 1024  // 4 KiB
	supervisorOrphanIDFmt = "orphan-%d"
)

// recoveryReason* are the canonical RecoveryReason strings emitted on
// EventClaudeProcessRecovered. Mirror the spec §4.5 closed set.
const (
	RecoveryReasonStdoutResumed       = "stdout_resumed"
	RecoveryReasonRateLimitExpired    = "rate_limit_window_expired"
	RecoveryReasonDiagnosticWait      = "diagnostic_recommended_wait"
	RecoveryReasonManualRetry         = "manual_retry"
	supervisorSelfHealOutcomeRecovery = "recovered"
	supervisorSelfHealOutcomeFailed   = "failed"
	supervisorSelfHealOutcomeRateLim  = "rate_limited"
	supervisorSelfHealOutcomeCapped   = "depth_capped"
)

// ErrSupervisorSaturated is returned by Supervisor.TryReserveSlot when
// the in-flight instance count has hit cfg.MaxConcurrent. The runner
// translates this into a typed command.claude.run failure rather than
// silently bypassing the supervisor.
var ErrSupervisorSaturated = fmt.Errorf("claude: supervisor saturated (max_concurrent reached)")

// SupervisorSink is the egress contract — one method per outbound
// envelope type. The production implementation lives in
// cmd/bridge/main.go (wsSupervisorSink); tests use a recording fake.
//
// All methods MUST be non-blocking by contract — the callers may run
// from inside a probe goroutine that holds no locks but that other
// goroutines may be waiting on (e.g. through Touch). A slow sink would
// stall every supervised instance.
type SupervisorSink interface {
	OnSpawned(ev protocol.EventClaudeProcessSpawned)
	OnHealthcheck(ev protocol.EventClaudeProcessHealthcheck)
	OnStalled(ev protocol.EventClaudeProcessStalled)
	OnCrashed(ev protocol.EventClaudeProcessCrashed)
	OnRecovered(ev protocol.EventClaudeProcessRecovered)
	OnDiagnosed(ev protocol.EventClaudeProcessDiagnosed)
}

// stderrRing is a fixed-capacity append-only byte ring used to hold
// the most recent stderrRingCap bytes of subprocess stderr. The
// stalled / crashed envelopes ship the last stderrTailCap bytes.
//
// Implementation note: a true ring would do circular indexing, but
// the supervisor only ever calls Tail() at most twice per instance
// (one stalled emit + one crashed emit) so a slice-with-trim is both
// simpler to reason about and has indistinguishable performance.
type stderrRing struct {
	mu  sync.Mutex
	buf []byte
}

func newStderrRing() *stderrRing {
	return &stderrRing{buf: make([]byte, 0, stderrRingCap)}
}

func (r *stderrRing) Append(p []byte) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.buf = append(r.buf, p...)
	if len(r.buf) > stderrRingCap {
		// Drop the oldest bytes — a single trim is fine because the
		// 16 KiB cap is so small that copying ~16 KiB on every
		// append-overflow is negligible (stderr is debug-level
		// chatter, not a hot path).
		drop := len(r.buf) - stderrRingCap
		copy(r.buf, r.buf[drop:])
		r.buf = r.buf[:stderrRingCap]
	}
}

// Tail returns at most stderrTailCap bytes from the end of the ring,
// plus a boolean signalling whether older bytes were truncated.
func (r *stderrRing) Tail() (string, bool) {
	r.mu.Lock()
	defer r.mu.Unlock()
	if len(r.buf) <= stderrTailCap {
		// A tail size equal to the whole buffer might still represent
		// a truncated history if the buffer is at its 16 KiB cap, but
		// callers only care about "the bytes I'm seeing fit fully" —
		// that branch IS truncated only when the upstream stream
		// produced more than stderrTailCap bytes total. We approximate
		// "truncated" as "the buffer is at cap" which is the common
		// failure-mode signal the iOS UI cares about.
		return string(r.buf), len(r.buf) >= stderrRingCap
	}
	return string(r.buf[len(r.buf)-stderrTailCap:]), true
}

// instance is the per-supervised-process record. All fields are
// guarded by Supervisor.mu — the probe goroutine snapshots under lock
// then releases before any I/O.
type instance struct {
	sessionID      string
	pid            int
	prompt         string
	model          string
	args           []string
	permissionMode string
	projectDir     string
	startedAt      time.Time
	lastStdoutAt   time.Time
	state          State
	// lastEmitForState is the last wall-clock time the supervisor
	// emitted a healthcheck for the current state. Used to coalesce
	// repeat-state emissions to once per cfg.HealthcheckCoalesce.
	lastEmitForState time.Time
	stderrRing       *stderrRing
	cancel           context.CancelFunc
	gen              uint64
	correlationID    string
	// orphan flags this instance as a pgrep-adopted entry; diagnostics
	// are disabled for orphans (we have no prompt/correlation context).
	orphan bool
	// staleEmitted is true once the stalled envelope has fired for
	// the current stale-episode. Cleared on every transition out of
	// stale so a stale → running → stale chain re-emits.
	staleEmitted bool
}

// rateLimitCache holds per-session rate-limit reset deadlines. A
// stale-trigger evaluation hits MarkRateLimit-recorded windows first
// so the supervisor never spawns a diagnostic for a known
// rate-limit-suspended instance (cost guard per spec §8).
type rateLimitCache struct {
	mu      sync.Mutex
	resetAt map[string]time.Time
}

func newRateLimitCache() *rateLimitCache {
	return &rateLimitCache{resetAt: make(map[string]time.Time)}
}

func (c *rateLimitCache) mark(sessionID string, resetAt time.Time) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.resetAt[sessionID] = resetAt
}

// active returns true if the cache says sessionID is still inside the
// rate-limit window relative to now. Expired windows are evicted
// in-line so repeated stale-trigger evaluations don't accumulate
// stale entries.
func (c *rateLimitCache) active(sessionID string, now time.Time) bool {
	c.mu.Lock()
	defer c.mu.Unlock()
	t, ok := c.resetAt[sessionID]
	if !ok {
		return false
	}
	if !now.Before(t) {
		delete(c.resetAt, sessionID)
		return false
	}
	return true
}

// supervisorClock allows tests to inject a deterministic clock without
// having to touch the production now() call sites. Default is the
// wall clock; tests substitute a manual clock that ticks under their
// control.
type supervisorClock interface {
	Now() time.Time
}

type wallClock struct{}

func (wallClock) Now() time.Time { return time.Now() }

// processProbe is the platform abstraction for the kill -0 / RSS / CPU
// sampling done on every probe tick. Tests substitute a fake that
// returns canned values; production uses the syscall-backed default.
type processProbe interface {
	// Alive returns true if the OS still owns a process at pid.
	Alive(pid int) bool
	// Sample returns the most recently observed RSS (KB) and 1-second
	// CPU% for pid. Both fields are best-effort; callers tolerate 0.
	Sample(pid int) (rssKB int64, cpu1s float64)
}

type defaultProbe struct{}

func (defaultProbe) Alive(pid int) bool {
	if pid <= 0 {
		return false
	}
	// Signal 0 is "no signal, just permission/existence check" per
	// kill(2) — we use it as the canonical liveness probe.
	if err := syscall.Kill(pid, 0); err != nil {
		return false
	}
	return true
}

func (defaultProbe) Sample(_ int) (int64, float64) {
	// Per spec §4.2 + spec §5.2 the production implementation calls
	// getrusage twice per probe to derive a 1-second CPU%. The full
	// platform-specific impl is out of scope for this layer (the
	// envelope tolerates zeros as best-effort) — return 0/0 so the
	// envelope still serialises correctly. iOS treats both as
	// best-effort gauges.
	return 0, 0
}

// orphanScanner is the platform abstraction for the
// `pgrep -f 'claude.*--output-format'` startup sweep. Tests inject a
// fake list; production uses pgrepOrphanScanner.
type orphanScanner interface {
	Scan(ctx context.Context) ([]int, error)
}

// pgrepOrphanScanner shells out to pgrep -f for V1.x system-wide
// orphan adoption (Q4 default per the user's locked decisions).
type pgrepOrphanScanner struct{}

func (pgrepOrphanScanner) Scan(ctx context.Context) ([]int, error) {
	cmd := exec.CommandContext(ctx, "pgrep", "-f", "claude.*--output-format")
	out, err := cmd.Output()
	if err != nil {
		// pgrep returns exit code 1 when no matches — treat as empty.
		var ee *exec.ExitError
		if asExitErr(err, &ee) && ee.ExitCode() == 1 {
			return nil, nil
		}
		return nil, fmt.Errorf("pgrep: %w", err)
	}
	pids := make([]int, 0)
	for _, line := range strings.Split(strings.TrimSpace(string(out)), "\n") {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		pid, perr := strconv.Atoi(line)
		if perr != nil {
			continue
		}
		pids = append(pids, pid)
	}
	return pids, nil
}

// asExitErr is a tiny errors.As helper that avoids importing errors
// just for the type assertion. Returns true if target now points at
// an *exec.ExitError unwrapped from err.
func asExitErr(err error, target **exec.ExitError) bool {
	for cur := err; cur != nil; {
		if e, ok := cur.(*exec.ExitError); ok {
			*target = e
			return true
		}
		type unwrapper interface{ Unwrap() error }
		u, ok := cur.(unwrapper)
		if !ok {
			return false
		}
		cur = u.Unwrap()
	}
	return false
}

// Supervisor owns the per-instance state machine + probe loop. A
// single Supervisor is shared across the whole bridge process; the
// runner calls Register/Touch/Unregister around each Run().
//
// Construct via NewSupervisor; cmd/bridge/main.go injects the
// SupervisorSink at startup via SetSink.
type Supervisor struct {
	cfg    *config.SupervisorConfig
	logger *slog.Logger
	clock  supervisorClock
	probe  processProbe
	scan   orphanScanner

	mu        sync.Mutex
	instances map[string]*instance
	nextGen   uint64
	sink      SupervisorSink

	rateLimitCache  *rateLimitCache
	diagnosticDepth atomic.Int32

	// ctx + cancel govern the probe goroutines. ctx is derived from
	// the parent context handed to NewSupervisor; cancel is fired by
	// Shutdown to drain the WaitGroup.
	ctx        context.Context
	cancelFunc context.CancelFunc
	wg         sync.WaitGroup

	// diagnosticExec is the injectable command factory used by the
	// diagnostic spawn helper. Defaults to exec.CommandContext;
	// tests override it with a fixture player.
	diagnosticExec ExecCommandFn

	// diagnosticBinary is the binary the diagnostic spawn invokes.
	// Defaults to "claude"; tests override to point at a fake.
	diagnosticBinary string
}

// NewSupervisor builds a Supervisor wired to the given config. The
// caller MUST call Shutdown(ctx) at process teardown so the probe
// goroutines drain cleanly.
//
// If logger is nil a no-op default is substituted so call sites need
// not check.
func NewSupervisor(parentCtx context.Context, cfg *config.SupervisorConfig, logger *slog.Logger) *Supervisor {
	if logger == nil {
		logger = slog.Default()
	}
	if parentCtx == nil {
		parentCtx = context.Background()
	}
	ctx, cancel := context.WithCancel(parentCtx)
	return &Supervisor{
		cfg:              cfg,
		logger:           logger,
		clock:            wallClock{},
		probe:            defaultProbe{},
		scan:             pgrepOrphanScanner{},
		instances:        make(map[string]*instance),
		rateLimitCache:   newRateLimitCache(),
		ctx:              ctx,
		cancelFunc:       cancel,
		diagnosticExec:   exec.CommandContext,
		diagnosticBinary: "claude",
	}
}

// SetSink installs the SupervisorSink. cmd/bridge/main.go invokes
// this once at startup with a wsSupervisorSink. Tests pass a
// recording fake. Safe to call before Register.
func (s *Supervisor) SetSink(sink SupervisorSink) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.sink = sink
}

// SetClock injects a deterministic clock for tests. Production
// callers leave the wall clock in place.
func (s *Supervisor) SetClock(c supervisorClock) {
	if c == nil {
		return
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	s.clock = c
}

// SetProbe injects a fake process probe for tests. Production uses
// the syscall-backed default.
func (s *Supervisor) SetProbe(p processProbe) {
	if p == nil {
		return
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	s.probe = p
}

// SetOrphanScanner injects a fake pgrep replacement for tests.
func (s *Supervisor) SetOrphanScanner(o orphanScanner) {
	if o == nil {
		return
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	s.scan = o
}

// SetDiagnosticExec / SetDiagnosticBinary let tests substitute the
// diagnostic spawn target without touching the production binary.
func (s *Supervisor) SetDiagnosticExec(fn ExecCommandFn) {
	if fn == nil {
		return
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	s.diagnosticExec = fn
}

func (s *Supervisor) SetDiagnosticBinary(name string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.diagnosticBinary = name
}

// TryReserveSlot enforces cfg.MaxConcurrent. Returns
// ErrSupervisorSaturated if the in-flight instance count has hit the
// cap. Otherwise returns nil — Register must follow shortly after.
//
// The slot accounting is implicit: Register adds to the map on
// success, Unregister removes. TryReserveSlot is a separate call
// (rather than baked into Register) so the runner can decide before
// going to the trouble of pipe wiring + cmd.Start.
func (s *Supervisor) TryReserveSlot() error {
	if s == nil || s.cfg == nil || !s.cfg.Enabled {
		return nil
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	if len(s.instances) >= s.cfg.MaxConcurrent {
		return ErrSupervisorSaturated
	}
	return nil
}

// RegisterInput captures the per-instance metadata the runner hands
// in at spawn time. Kept as a struct (rather than a long arglist) so
// the call site stays readable.
type RegisterInput struct {
	SessionID      string
	PID            int
	Prompt         string
	Model          string
	Args           []string
	PermissionMode string
	ProjectDir     string
	CorrelationID  string
	Cancel         context.CancelFunc
}

// Register adds an instance to the supervised set, fires the
// `event.claude.process.spawned` envelope, and starts the probe
// goroutine. Returns the per-instance generation token (used by
// Unregister to compare-and-delete on a session-id collision).
//
// Touch and any subsequent Register-with-same-sessionID racing to
// install themselves are guarded by the per-Supervisor mutex.
//
// When the supervisor is disabled, Register is a no-op that returns 0.
func (s *Supervisor) Register(in RegisterInput) uint64 {
	if s == nil || s.cfg == nil || !s.cfg.Enabled {
		return 0
	}
	now := s.clock.Now()
	s.mu.Lock()
	if prev, exists := s.instances[in.SessionID]; exists {
		// Rare — a prior Run for the same session_id is still mapped.
		// Treat the old entry as superseded: cancel it and overwrite.
		if prev.cancel != nil {
			prev.cancel()
		}
		s.bumpStateMetricLocked(prev.state, -1)
	}
	s.nextGen++
	gen := s.nextGen
	inst := &instance{
		sessionID:        in.SessionID,
		pid:              in.PID,
		prompt:           in.Prompt,
		model:            in.Model,
		args:             append([]string(nil), in.Args...),
		permissionMode:   in.PermissionMode,
		projectDir:       in.ProjectDir,
		startedAt:        now,
		lastStdoutAt:     time.Time{},
		state:            StateStarting,
		lastEmitForState: now,
		stderrRing:       newStderrRing(),
		cancel:           in.Cancel,
		gen:              gen,
		correlationID:    in.CorrelationID,
	}
	s.instances[in.SessionID] = inst
	s.bumpStateMetricLocked(StateStarting, 1)
	sink := s.sink
	s.mu.Unlock()

	if sink != nil {
		sink.OnSpawned(protocol.EventClaudeProcessSpawned{
			SessionID:      in.SessionID,
			PID:            in.PID,
			StartedAt:      now.UTC().Format(time.RFC3339Nano),
			Model:          in.Model,
			Args:           sanitizeArgs(in.Args),
			PermissionMode: in.PermissionMode,
			ProjectDir:     in.ProjectDir,
		})
	}

	s.wg.Add(1)
	go s.probeLoop(in.SessionID, gen)
	return gen
}

// sanitizeArgs returns a copy of args minus the trailing positional
// prompt — the spec §4.1 PII guard says the orchestrator instruction
// never leaves the bridge through the spawned envelope. We
// approximate "trailing positional" as the last element that does not
// look like a flag (no leading "-"); paired flags (--key value) are
// trivially preserved.
func sanitizeArgs(args []string) []string {
	if len(args) == 0 {
		return nil
	}
	out := make([]string, len(args))
	copy(out, args)
	last := len(out) - 1
	if last >= 0 && !strings.HasPrefix(out[last], "-") {
		// Trim only when the prior element is itself NOT a flag
		// expecting a value. Heuristic: the runner always builds
		// args as `... <flag> <value> <prompt>` so the prompt is
		// the final element AND the second-to-last element is a
		// flag value (also without a leading "-"). To stay safe,
		// we always strip the last element when it doesn't start
		// with "-" — the runner contract guarantees the prompt is
		// always the trailing positional.
		out = out[:last]
	}
	return out
}

// Touch bumps lastStdoutAt for the named session and, if the instance
// was in starting/idle/stale, transitions it back to running and
// emits the corresponding envelope.
//
// Cheap by design — invoked from the parser hot path (one call per
// stdout line). Falls through silently when the session is unknown
// (an unregistered Touch is the common case during Shutdown).
func (s *Supervisor) Touch(sessionID string) {
	if s == nil || s.cfg == nil || !s.cfg.Enabled {
		return
	}
	now := s.clock.Now()
	s.mu.Lock()
	inst, ok := s.instances[sessionID]
	if !ok {
		s.mu.Unlock()
		return
	}
	prevState := inst.state
	inst.lastStdoutAt = now
	var (
		emitRecover *protocol.EventClaudeProcessRecovered
		emitHealth  *protocol.EventClaudeProcessHealthcheck
	)
	switch prevState {
	case StateStarting:
		s.transitionLocked(inst, StateRunning, now)
		emitHealth = s.buildHealthcheckLocked(inst, now)
	case StateIdle:
		s.transitionLocked(inst, StateRunning, now)
		emitHealth = s.buildHealthcheckLocked(inst, now)
	case StateStale, StateDiagnosing:
		s.transitionLocked(inst, StateRunning, now)
		recovered := protocol.EventClaudeProcessRecovered{
			OldSessionID:   inst.sessionID,
			NewSessionID:   inst.sessionID,
			RecoveryReason: RecoveryReasonStdoutResumed,
			RecoveredAt:    now.UTC().Format(time.RFC3339Nano),
		}
		emitRecover = &recovered
		telemetry.ClaudeSupervisorSelfHealsTotal.Add(supervisorSelfHealOutcomeRecovery, 1)
		emitHealth = s.buildHealthcheckLocked(inst, now)
	case StateRateLimited:
		s.transitionLocked(inst, StateRunning, now)
		recovered := protocol.EventClaudeProcessRecovered{
			OldSessionID:   inst.sessionID,
			NewSessionID:   inst.sessionID,
			RecoveryReason: RecoveryReasonRateLimitExpired,
			RecoveredAt:    now.UTC().Format(time.RFC3339Nano),
		}
		emitRecover = &recovered
		telemetry.ClaudeSupervisorSelfHealsTotal.Add(supervisorSelfHealOutcomeRecovery, 1)
		emitHealth = s.buildHealthcheckLocked(inst, now)
	default:
		// running → running: only emit a healthcheck if the
		// coalesce window has elapsed.
		if now.Sub(inst.lastEmitForState) >= s.cfg.HealthcheckCoalesce {
			inst.lastEmitForState = now
			emitHealth = s.buildHealthcheckLocked(inst, now)
		}
	}
	sink := s.sink
	s.mu.Unlock()

	if sink == nil {
		return
	}
	if emitRecover != nil {
		sink.OnRecovered(*emitRecover)
	}
	if emitHealth != nil {
		sink.OnHealthcheck(*emitHealth)
	}
}

// RecordStderr appends raw stderr bytes to the per-instance ring
// buffer. Surfaced verbatim on the next stalled / crashed envelope.
func (s *Supervisor) RecordStderr(sessionID string, p []byte) {
	if s == nil || s.cfg == nil || !s.cfg.Enabled {
		return
	}
	s.mu.Lock()
	inst, ok := s.instances[sessionID]
	s.mu.Unlock()
	if !ok {
		return
	}
	inst.stderrRing.Append(p)
}

// MarkRateLimit records a rate-limit window so the stale-trigger
// short-circuits to the rate_limited state instead of spawning a
// diagnostic. resetsAt is the unix-epoch seconds value claude
// reports on its rate_limit_event line.
func (s *Supervisor) MarkRateLimit(sessionID string, resetsAt int64) {
	if s == nil || s.cfg == nil || !s.cfg.Enabled {
		return
	}
	if resetsAt <= 0 {
		return
	}
	s.rateLimitCache.mark(sessionID, time.Unix(resetsAt, 0))
}

// Unregister removes the instance keyed by sessionID iff the stored
// generation matches gen. A non-matching gen is a stale defer from a
// superseded Run() and is a no-op (compare-and-delete pattern same as
// runner.unregisterActive). cause carries the cmd.Wait() outcome —
// nil on clean exit, non-nil to fire `event.claude.process.crashed`.
//
// completedCleanly distinguishes "exit 0 + EventSessionResult" from
// "exit 0 but stream-json never produced a result frame"; the runner
// passes true only when the parser's Result handler has fired.
func (s *Supervisor) Unregister(sessionID string, gen uint64, cause error, completedCleanly bool) {
	if s == nil || s.cfg == nil || !s.cfg.Enabled {
		return
	}
	now := s.clock.Now()
	s.mu.Lock()
	inst, ok := s.instances[sessionID]
	if !ok || inst.gen != gen {
		s.mu.Unlock()
		return
	}
	prevState := inst.state
	var (
		emitCrashed *protocol.EventClaudeProcessCrashed
		emitHealth  *protocol.EventClaudeProcessHealthcheck
	)
	switch {
	case cause != nil:
		s.transitionLocked(inst, StateCrashed, now)
		stderrTail, truncated := inst.stderrRing.Tail()
		_ = truncated
		exitCode, signal := decodeExitError(cause)
		ev := protocol.EventClaudeProcessCrashed{
			SessionID:  inst.sessionID,
			PID:        inst.pid,
			ExitCode:   exitCode,
			Signal:     signal,
			StderrTail: stderrTail,
			DurationMs: now.Sub(inst.startedAt).Milliseconds(),
			CrashedAt:  now.UTC().Format(time.RFC3339Nano),
		}
		emitCrashed = &ev
	case completedCleanly:
		s.transitionLocked(inst, StateCompleted, now)
		emitHealth = s.buildHealthcheckLocked(inst, now)
	default:
		// Exit 0 but no Result frame — treat as completed with a
		// zero-tokens healthcheck. The iOS UI can decide whether to
		// show this as success or a soft anomaly.
		s.transitionLocked(inst, StateCompleted, now)
		emitHealth = s.buildHealthcheckLocked(inst, now)
	}
	delete(s.instances, sessionID)
	s.bumpStateMetricLocked(prevState, -1)
	if cause == nil {
		// Completed transition counted by transitionLocked; subtract
		// the post-transition tick we just added by decrementing the
		// completed bucket too — we never report "completed" as a
		// live instance. The transitionLocked already added +1 for
		// completed; remove it here.
		s.bumpStateMetricLocked(StateCompleted, -1)
	} else {
		s.bumpStateMetricLocked(StateCrashed, -1)
	}
	sink := s.sink
	s.mu.Unlock()

	if sink != nil {
		if emitCrashed != nil {
			sink.OnCrashed(*emitCrashed)
		}
		if emitHealth != nil {
			sink.OnHealthcheck(*emitHealth)
		}
	}
}

// Shutdown cancels all probe goroutines and waits for them to exit.
// Idempotent — safe to call from defers in tests.
func (s *Supervisor) Shutdown(ctx context.Context) error {
	if s == nil {
		return nil
	}
	s.cancelFunc()
	doneCh := make(chan struct{})
	go func() {
		s.wg.Wait()
		close(doneCh)
	}()
	select {
	case <-doneCh:
		return nil
	case <-ctx.Done():
		return ctx.Err()
	}
}

// AdoptOrphans runs the system-wide pgrep scan exactly once at
// supervisor startup. Each PID becomes a synthetic instance with
// session_id = "orphan-{pid}" and state = running (we have no
// stdout-age signal for an orphan). Diagnostics are disabled for
// orphans because there's no prompt context to synthesise a useful
// diagnostic question.
//
// The scanner is pluggable so tests can inject a deterministic list.
func (s *Supervisor) AdoptOrphans(ctx context.Context) (int, error) {
	if s == nil || s.cfg == nil || !s.cfg.Enabled {
		return 0, nil
	}
	pids, err := s.scan.Scan(ctx)
	if err != nil {
		return 0, err
	}
	now := s.clock.Now()
	adopted := 0
	for _, pid := range pids {
		sessionID := fmt.Sprintf(supervisorOrphanIDFmt, pid)
		s.mu.Lock()
		if _, exists := s.instances[sessionID]; exists {
			s.mu.Unlock()
			continue
		}
		s.nextGen++
		gen := s.nextGen
		inst := &instance{
			sessionID:        sessionID,
			pid:              pid,
			model:            "unknown",
			args:             nil,
			startedAt:        now,
			lastStdoutAt:     now,
			state:            StateRunning,
			lastEmitForState: now,
			stderrRing:       newStderrRing(),
			gen:              gen,
			orphan:           true,
		}
		s.instances[sessionID] = inst
		s.bumpStateMetricLocked(StateRunning, 1)
		sink := s.sink
		s.mu.Unlock()
		if sink != nil {
			sink.OnSpawned(protocol.EventClaudeProcessSpawned{
				SessionID: sessionID,
				PID:       pid,
				StartedAt: now.UTC().Format(time.RFC3339Nano),
				Model:     "unknown",
			})
		}
		s.wg.Add(1)
		go s.probeLoop(sessionID, gen)
		adopted++
	}
	return adopted, nil
}

// CachedPrompt returns the prompt the runner registered for
// sessionID. Used by the inbound command.claude.process.retry handler
// in cmd/bridge/main.go to re-issue Run() with the same prompt.
// Returns ("", false) when the session is not currently supervised.
func (s *Supervisor) CachedPrompt(sessionID string) (string, bool) {
	if s == nil {
		return "", false
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	inst, ok := s.instances[sessionID]
	if !ok {
		return "", false
	}
	return inst.prompt, true
}

// State returns a snapshot of the named session's current state.
// Used by tests to assert transitions without exporting the
// internal instance struct.
func (s *Supervisor) State(sessionID string) (State, bool) {
	if s == nil {
		return "", false
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	inst, ok := s.instances[sessionID]
	if !ok {
		return "", false
	}
	return inst.state, true
}

// InstanceCount returns the number of supervised instances. Used by
// tests + the V1.x reviewer-suggested "saturation" assertion in the
// bridge runtime telemetry.
func (s *Supervisor) InstanceCount() int {
	if s == nil {
		return 0
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	return len(s.instances)
}

// transitionLocked moves an instance to a new state, updating the
// per-state Prometheus gauge and re-arming the coalesce window.
// Caller MUST hold s.mu.
func (s *Supervisor) transitionLocked(inst *instance, next State, now time.Time) {
	if inst.state == next {
		return
	}
	s.bumpStateMetricLocked(inst.state, -1)
	inst.state = next
	s.bumpStateMetricLocked(next, +1)
	inst.lastEmitForState = now
	if next != StateStale {
		inst.staleEmitted = false
	}
}

// bumpStateMetricLocked is a tiny helper that nudges the per-state
// expvar.Map by delta. Caller MUST hold s.mu.
func (s *Supervisor) bumpStateMetricLocked(st State, delta int64) {
	telemetry.ClaudeSupervisorInstancesTotal.Add(string(st), delta)
}

// buildHealthcheckLocked builds a healthcheck envelope under the
// caller's lock. Caller MUST hold s.mu.
func (s *Supervisor) buildHealthcheckLocked(inst *instance, now time.Time) *protocol.EventClaudeProcessHealthcheck {
	rss, cpu := s.probe.Sample(inst.pid)
	var ageMs int64
	if !inst.lastStdoutAt.IsZero() {
		ageMs = now.Sub(inst.lastStdoutAt).Milliseconds()
	}
	return &protocol.EventClaudeProcessHealthcheck{
		SessionID:       inst.sessionID,
		PID:             inst.pid,
		Status:          string(inst.state),
		LastStdoutAgeMs: ageMs,
		CurrentTokens:   0,
		MemoryRSSKB:     rss,
		CPUPercent1s:    cpu,
		ObservedAt:      now.UTC().Format(time.RFC3339Nano),
	}
}

// probeLoop is the per-instance liveness probe. It ticks at
// cfg.ProbeInterval, runs kill -0, samples stdout-age, evaluates
// state transitions and emits the corresponding envelopes.
//
// The loop exits when:
//   - s.ctx is cancelled (Shutdown), OR
//   - the instance is unregistered (sessionID no longer in the map), OR
//   - the instance's generation no longer matches gen.
func (s *Supervisor) probeLoop(sessionID string, gen uint64) {
	defer s.wg.Done()
	ticker := time.NewTicker(s.cfg.ProbeInterval)
	defer ticker.Stop()

	for {
		select {
		case <-s.ctx.Done():
			return
		case <-ticker.C:
			if !s.runProbeTick(sessionID, gen) {
				return
			}
		}
	}
}

// runProbeTick is the per-tick body. Returns false to signal the
// caller to exit the loop (instance unregistered or generation
// superseded).
func (s *Supervisor) runProbeTick(sessionID string, gen uint64) bool {
	now := s.clock.Now()
	s.mu.Lock()
	inst, ok := s.instances[sessionID]
	if !ok || inst.gen != gen {
		s.mu.Unlock()
		return false
	}
	pid := inst.pid
	prevState := inst.state
	stdoutAge := time.Duration(0)
	if !inst.lastStdoutAt.IsZero() {
		stdoutAge = now.Sub(inst.lastStdoutAt)
	}
	hadFirstStdout := !inst.lastStdoutAt.IsZero()
	correlationID := inst.correlationID
	orphan := inst.orphan
	startedAt := inst.startedAt
	s.mu.Unlock()

	// Liveness check OUTSIDE the lock so a slow syscall cannot
	// stall Touch / Register on the hot path.
	alive := s.probe.Alive(pid)
	if !alive {
		// Lost the process — emit crashed and exit the loop.
		s.markCrashedFromProbe(sessionID, gen, now, startedAt)
		return false
	}

	// State-transition evaluation under the lock.
	s.mu.Lock()
	inst, ok = s.instances[sessionID]
	if !ok || inst.gen != gen {
		s.mu.Unlock()
		return false
	}
	var (
		emitHealth     *protocol.EventClaudeProcessHealthcheck
		emitStalled    *protocol.EventClaudeProcessStalled
		runDiagnostic  bool
		diagnosticInst *instance
	)

	switch inst.state {
	case StateStarting:
		// No stdout yet — nothing to do until Touch fires.
	case StateRunning:
		if hadFirstStdout && stdoutAge >= s.cfg.StaleThreshold {
			s.transitionLocked(inst, StateStale, now)
			stderrTail, truncated := inst.stderrRing.Tail()
			selfHeal := s.cfg.SelfHealEnabled && !orphan && !s.rateLimitCache.active(sessionID, now)
			if !inst.staleEmitted {
				inst.staleEmitted = true
				ev := protocol.EventClaudeProcessStalled{
					SessionID:           sessionID,
					PID:                 pid,
					LastActivityAt:      inst.lastStdoutAt.UTC().Format(time.RFC3339Nano),
					StaleForMs:          stdoutAge.Milliseconds(),
					StderrTail:          stderrTail,
					StderrTailTruncated: truncated,
					SelfHealPending:     selfHeal,
				}
				emitStalled = &ev
			}
			// Decide self-heal arm now (still under lock).
			if !s.cfg.SelfHealEnabled || orphan {
				// Skip diagnostic.
			} else if s.rateLimitCache.active(sessionID, now) {
				s.transitionLocked(inst, StateRateLimited, now)
				telemetry.ClaudeSupervisorSelfHealsTotal.Add(supervisorSelfHealOutcomeRateLim, 1)
			} else {
				runDiagnostic = true
				diagnosticInst = inst
			}
		} else if hadFirstStdout && stdoutAge >= s.cfg.IdleThreshold {
			s.transitionLocked(inst, StateIdle, now)
			emitHealth = s.buildHealthcheckLocked(inst, now)
		} else if now.Sub(inst.lastEmitForState) >= s.cfg.HealthcheckCoalesce {
			inst.lastEmitForState = now
			emitHealth = s.buildHealthcheckLocked(inst, now)
		}
	case StateIdle:
		if hadFirstStdout && stdoutAge >= s.cfg.StaleThreshold {
			s.transitionLocked(inst, StateStale, now)
			stderrTail, truncated := inst.stderrRing.Tail()
			selfHeal := s.cfg.SelfHealEnabled && !orphan && !s.rateLimitCache.active(sessionID, now)
			if !inst.staleEmitted {
				inst.staleEmitted = true
				ev := protocol.EventClaudeProcessStalled{
					SessionID:           sessionID,
					PID:                 pid,
					LastActivityAt:      inst.lastStdoutAt.UTC().Format(time.RFC3339Nano),
					StaleForMs:          stdoutAge.Milliseconds(),
					StderrTail:          stderrTail,
					StderrTailTruncated: truncated,
					SelfHealPending:     selfHeal,
				}
				emitStalled = &ev
			}
			if !s.cfg.SelfHealEnabled || orphan {
				// Skip diagnostic.
			} else if s.rateLimitCache.active(sessionID, now) {
				s.transitionLocked(inst, StateRateLimited, now)
				telemetry.ClaudeSupervisorSelfHealsTotal.Add(supervisorSelfHealOutcomeRateLim, 1)
			} else {
				runDiagnostic = true
				diagnosticInst = inst
			}
		} else if now.Sub(inst.lastEmitForState) >= s.cfg.HealthcheckCoalesce {
			inst.lastEmitForState = now
			emitHealth = s.buildHealthcheckLocked(inst, now)
		}
	case StateStale, StateRateLimited, StateDiagnosing:
		// Coalesced healthcheck only — terminal transitions out of
		// these states are driven by Touch (recovery) or Unregister.
		if now.Sub(inst.lastEmitForState) >= s.cfg.HealthcheckCoalesce {
			inst.lastEmitForState = now
			emitHealth = s.buildHealthcheckLocked(inst, now)
		}
	}

	_ = prevState
	_ = correlationID

	sink := s.sink
	s.mu.Unlock()

	if sink != nil {
		if emitHealth != nil {
			sink.OnHealthcheck(*emitHealth)
		}
		if emitStalled != nil {
			sink.OnStalled(*emitStalled)
		}
	}

	if runDiagnostic && diagnosticInst != nil {
		// Spawn diagnostic in its own goroutine so the probe loop
		// stays responsive. The diagnostic helper handles its own
		// depth guard, timeout and result emission.
		s.wg.Add(1)
		go func(inst *instance) {
			defer s.wg.Done()
			s.runDiagnostic(inst)
		}(diagnosticInst)
	}
	return true
}

// markCrashedFromProbe handles the "kill -0 returned ESRCH" branch.
// Pulled out so runProbeTick stays small enough to read top-to-bottom.
func (s *Supervisor) markCrashedFromProbe(sessionID string, gen uint64, now time.Time, startedAt time.Time) {
	s.mu.Lock()
	inst, ok := s.instances[sessionID]
	if !ok || inst.gen != gen {
		s.mu.Unlock()
		return
	}
	prevState := inst.state
	s.transitionLocked(inst, StateCrashed, now)
	stderrTail, _ := inst.stderrRing.Tail()
	pid := inst.pid
	delete(s.instances, sessionID)
	s.bumpStateMetricLocked(prevState, 0) // already counted by transitionLocked
	s.bumpStateMetricLocked(StateCrashed, -1)
	sink := s.sink
	s.mu.Unlock()

	if sink != nil {
		sink.OnCrashed(protocol.EventClaudeProcessCrashed{
			SessionID:  sessionID,
			PID:        pid,
			ExitCode:   -1,
			Signal:     "SIGKILL", // best-effort attribution; we lost cmd.Wait()
			StderrTail: stderrTail,
			DurationMs: now.Sub(startedAt).Milliseconds(),
			CrashedAt:  now.UTC().Format(time.RFC3339Nano),
		})
	}
}

// decodeExitError extracts (exit_code, signal_name) from a
// cmd.Wait() error. Tolerates non-ExitError causes by returning
// (-1, "").
func decodeExitError(err error) (int, string) {
	if err == nil {
		return 0, ""
	}
	var ee *exec.ExitError
	if asExitErr(err, &ee) {
		ws, ok := ee.Sys().(syscall.WaitStatus)
		if !ok {
			return ee.ExitCode(), ""
		}
		if ws.Signaled() {
			return 128 + int(ws.Signal()), signalName(ws.Signal())
		}
		return ws.ExitStatus(), ""
	}
	return -1, ""
}

// signalName maps a syscall.Signal to its canonical string. Limited
// to the signals the supervisor cares about (KILL, TERM, INT, STOP).
func signalName(sig syscall.Signal) string {
	switch sig {
	case syscall.SIGKILL:
		return "SIGKILL"
	case syscall.SIGTERM:
		return "SIGTERM"
	case syscall.SIGINT:
		return "SIGINT"
	case syscall.SIGSTOP:
		return "SIGSTOP"
	default:
		return sig.String()
	}
}
