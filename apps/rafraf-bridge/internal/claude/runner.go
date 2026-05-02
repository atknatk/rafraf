// Package claude wraps the `claude -p --output-format stream-json` subprocess
// and exposes a typed event stream to the rest of the bridge.
//
// T0.5.5 introduces:
//
//   - Runner with config-aware argument and environment construction
//     (ANTHROPIC_API_KEY excluded; CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1
//     injected when the request or config opts in).
//   - EventSink interface (docs/11_Bridge_Spec.md §3.4) for typed callbacks.
//   - Abort(sessionID) — cooperative cancel via context, with a brief
//     grace window for the subprocess to terminate.
//   - AuthCheck(ctx) — startup health probe that runs `claude auth status`.
//   - ExecCommandFn — injectable command factory so tests can substitute
//     `cat testdata/*.jsonl` for the real claude binary.
//
// T0.5.6 replaces the placeholder Parser with full stream-json dispatch
// + state tracking; the Runner contract here is unchanged. The same task
// folds in the M1 reviewer fix to activeRuns (compare-and-delete via a
// generation counter).
package claude

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"log/slog"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/trace"

	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/config"
	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/protocol"
	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/telemetry"
)

// claudeTracerName is the OTel instrumentation library identifier used
// by the runner + parser; matches the convention "<module>/<package>".
const claudeTracerName = "rafraf-bridge/claude"

// ErrRunnerBusy is returned by Run() when a permission broker is wired
// AND another concurrent Run is already holding the broker's
// SetRequestHandler slot. V1.3 reviewer H1 fix: rather than silently
// overwriting the predecessor's closure (which would misroute
// permission_request envelopes with the wrong correlation_id), we fail
// loud so the caller can observe and retry.
var ErrRunnerBusy = errors.New("claude: runner busy (permission broker handler held by another run)")

// abortGracePeriod is how long Abort() lingers after cancelling the run
// context, giving the subprocess a chance to flush stdout before any
// follow-up Run() reuses the binary slot. SIGKILL escalation is handled
// implicitly by exec.CommandContext when the context is cancelled.
const abortGracePeriod = 100 * time.Millisecond

// stderrDrainBufSize bounds a single read from the subprocess's stderr
// pipe. Lines longer than this are split across multiple log entries —
// acceptable since stderr is debug-only diagnostic noise.
const stderrDrainBufSize = 4096

// stdoutMaxLineSize caps a single stream-json line at 16 MiB. The Python
// reference (apps/agent/agent/runners/claude_runner.py) does not bound
// line length explicitly; this matches the spike's safety ceiling.
const stdoutMaxLineSize = 16 << 20 // 16 MiB

// stdoutInitialBufSize seeds the bufio.Scanner buffer at 1 MiB so typical
// lines never trigger an allocation while leaving headroom up to the cap.
const stdoutInitialBufSize = 1 << 20 // 1 MiB

// activeRun pairs a per-run cancel function with a monotonically-increasing
// generation counter. The generation is the compare-and-delete token that
// keeps unregisterActive from clobbering a newer run's entry — see the
// T0.5.5 reviewer M1 fix folded into T0.5.6 and the dedicated
// TestRunner_ConcurrentSameSession_GenSafetyKeepsNewer test.
type activeRun struct {
	cancel context.CancelFunc
	gen    uint64
}

// Runner spawns and supervises `claude -p --output-format stream-json`
// subprocesses. A single Runner can host multiple concurrent sessions
// keyed by RunRequest.SessionID; each may be cancelled independently
// via Abort.
//
// V1.2 adds permission-broker plumbing: when the runner is constructed
// with a non-empty PermissionSockPath the per-session settings overlay
// registers the rafraf-perm-hook binary as a PreToolUse hook and the
// subprocess env carries RAFRAF_BRIDGE_PERM_SOCK pointing at the same
// path. When PermissionHookPath cannot be resolved (e.g. dev mode
// where the sibling binary isn't built) the runner logs a warning and
// SKIPS the --settings injection so the dev workflow still works.
//
// V1.3 promotes permissionBroker to a first-class runner dependency:
// at Run-time the runner installs a SetRequestHandler closure that
// forwards each broker request through the per-run EventSink (so the
// envelope carries the right correlation_id), then clears it on Run
// exit. The broker stays alive across runs but only one runner can be
// active at a time in V1 — see the LWW invariant note in Run().
type Runner struct {
	cfg    *config.Config
	logger *slog.Logger

	// permissionSockPath is the UDS path the broker is listening on.
	// Empty → permission injection disabled (V1.0/V1.1 compatibility
	// + tests that don't care about the hook).
	permissionSockPath string
	// permissionHookPath is the absolute path to the rafraf-perm-hook
	// binary. Resolved via os.Executable() + sibling lookup at
	// NewRunner-time. Empty → injection disabled.
	permissionHookPath string
	// permissionBroker, when non-nil, has its SetRequestHandler hook
	// flipped on/off around each Run() so per-run envelopes carry the
	// originating command.claude.run correlation_id. Nil → V1.2
	// degraded path (broker startup failed); the runner still spawns
	// claude but the broker resolves every hook request as deny.
	permissionBroker PermissionBroker

	mu         sync.Mutex
	activeRuns map[string]activeRun // sessionID → cancel + generation
	nextGen    uint64               // monotonic, advanced under mu
	// permHandlerOwner is the sessionID currently owning the broker's
	// SetRequestHandler slot, or "" when no Run holds it. CAS-guarded
	// so a second concurrent Run with a non-nil broker fails loud
	// (ErrRunnerBusy) instead of silently overwriting the first run's
	// closure — V1.3 reviewer H1 fix.
	permHandlerOwner atomic.Pointer[string]
}

// RunRequest is the per-invocation control surface. Empty fields fall
// back to the corresponding config.Config values where applicable.
type RunRequest struct {
	// Prompt is the orchestrator instruction passed as claude's positional
	// argument. Required.
	Prompt string
	// SessionID is non-empty to resume an existing session via
	// `claude --resume <id>`; empty starts a fresh session. When non-empty
	// the SessionID is also the key under which Abort() can cancel the run.
	SessionID string
	// PermissionMode overrides config.PermissionMode for this run. Empty
	// uses the config default.
	PermissionMode string
	// ProjectDir overrides config.ProjectDir (the subprocess cwd) for this
	// run. Empty uses the config default.
	ProjectDir string
	// AgentTeams, when true, injects CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1
	// into the subprocess env. Logical OR with config.AgentTeams.
	AgentTeams bool
	// UserID is recorded on log lines for correlation with backend
	// audit trails; opaque to the runner.
	UserID string
}

// EventSink receives one callback per parsed stream-json event. Method
// names mirror the protocol.EventSession* type catalogue. Implementations
// are expected to be cheap (typically a single envelope build + queue
// push); blocking work belongs downstream of the sink.
//
// T0.5.6 wires up dispatch — the Parser now invokes one of these methods
// per recognised stream-json frame.
//
// V1.3 adds OnPermissionRequest. Unlike the other callbacks, this one is
// NOT driven by the stream-json parser; it is invoked by the
// permission.Broker via a closure the runner installs at Run-time so
// the per-run sink (which carries the originating
// command.claude.run correlation_id) is the egress path. This keeps
// envelope routing aligned with the rest of the per-RPC events.
type EventSink interface {
	OnInit(ev protocol.EventSessionInit) error
	OnAssistant(ev protocol.EventSessionAssistant) error
	OnUser(ev protocol.EventSessionUser) error
	OnStream(ev protocol.EventSessionStream) error
	OnTaskStarted(ev protocol.EventSessionTaskStarted) error
	OnTaskProgress(ev protocol.EventSessionTaskProgress) error
	OnTaskNotification(ev protocol.EventSessionTaskNotification) error
	OnRateLimit(ev protocol.EventSessionRateLimit) error
	OnHookStarted(ev protocol.EventSessionHookStarted) error
	OnHookResponse(ev protocol.EventSessionHookResponse) error
	OnResult(ev protocol.EventSessionResult) error
	OnPermissionRequest(ev protocol.EventSessionPermissionRequest) error
}

// PermissionBroker is the narrow contract the runner needs from the
// permission package. It is declared locally (rather than imported from
// internal/permission) so the claude package never takes a dependency
// on internal/permission — that import direction would create a cycle
// the moment internal/permission needs anything from internal/claude.
//
// The runner uses SetRequestHandler to install a closure that forwards
// each broker request through the per-run EventSink. Closures take
// precedence over previous handlers (LWW); see the V1 invariant note in
// Run().
type PermissionBroker interface {
	SetRequestHandler(fn func(ev protocol.EventSessionPermissionRequest))
}

// ExecCommandFn matches exec.CommandContext's signature so tests can
// substitute a stub that emits canned stream-json from a fixture file.
type ExecCommandFn func(ctx context.Context, name string, args ...string) *exec.Cmd

// NewRunner constructs a Runner. logger may be nil; a no-op default is
// substituted in that case so call sites need not check.
//
// V1.3 callers should follow up with SetPermissionContext(broker, sock, hook)
// to enable the PreToolUse hook injection. NewRunner alone preserves
// the V1.0/V1.1 behaviour (no hook, no settings overlay).
func NewRunner(cfg *config.Config, logger *slog.Logger) *Runner {
	if logger == nil {
		logger = slog.New(slog.NewTextHandler(io.Discard, nil))
	}
	return &Runner{
		cfg:        cfg,
		logger:     logger,
		activeRuns: make(map[string]activeRun),
	}
}

// SetPermissionContext configures the V1.2/V1.3 PreToolUse hook
// injection. broker, when non-nil, gets its SetRequestHandler closure
// installed at Run-time so per-run envelopes carry the originating
// command.claude.run correlation_id. sockPath is the broker UDS the
// hook will dial; hookPath is the absolute path to the rafraf-perm-hook
// binary. Either path being empty disables --settings injection (the
// runner logs at first Run() and proceeds plain).
//
// The runner stores everything verbatim — it does NOT validate that
// hookPath exists at SetPermissionContext-time so callers can wire
// the deferred hook discovery (typical: bridge startup hits this with
// the path it just resolved via os.Executable() sibling lookup).
//
// V1 ships at most one active claude subprocess per bridge process at a
// time, so the LWW SetRequestHandler discipline (each Run() overwrites,
// then defers clearing) is safe. If a future iteration multiplexes
// runners against a single broker this contract has to change — the
// broker would need a per-correlation map of handlers instead of one
// process-wide slot.
func (r *Runner) SetPermissionContext(broker PermissionBroker, sockPath, hookPath string) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.permissionBroker = broker
	r.permissionSockPath = sockPath
	r.permissionHookPath = hookPath
}

// Run executes a `claude -p` subprocess and pipes its stdout through the
// parser, which dispatches typed events to sink. Run blocks until the
// subprocess exits or ctx is cancelled. Stderr is drained to the runner
// logger at debug level.
func (r *Runner) Run(ctx context.Context, req RunRequest, sink EventSink) error {
	return r.runWithExec(ctx, req, sink, exec.CommandContext)
}

// runWithExec is the testable variant — it accepts an injectable command
// factory so tests can swap claude for a deterministic fixture player.
func (r *Runner) runWithExec(
	ctx context.Context,
	req RunRequest,
	sink EventSink,
	execCmd ExecCommandFn,
) error {
	telemetry.ClaudeSubprocessActive.Add(1)
	telemetry.ClaudeSubprocessTotal.Add(1)
	defer telemetry.ClaudeSubprocessActive.Add(-1)

	// Per-run context — derived so Abort() can target this single run
	// without taking down the parent context.
	runCtx, cancel := context.WithCancel(ctx)
	defer cancel()

	if req.SessionID != "" {
		gen := r.registerActive(req.SessionID, cancel)
		defer r.unregisterActive(req.SessionID, gen)
	}

	// V1.2 — write the per-session settings overlay (registers the
	// PreToolUse hook) and arrange for cleanup on exit. The path is
	// piped into buildArgs via the optional --settings flag.
	settingsPath, settingsCleanup := r.preparePermissionOverlay(req)
	defer settingsCleanup()

	// V1.3 — install the broker→sink closure BEFORE the subprocess
	// spawn so any PreToolUse hook fired during init is already routed
	// through the correct per-run envelope path. Cleared on exit so a
	// late hook firing against a torn-down sink fails silently rather
	// than panicking.
	//
	// LWW invariant: V1 ships at most one active claude subprocess per
	// bridge, so a single SetRequestHandler slot on the broker is
	// sufficient. The defer below restores nil when this run exits —
	// concurrent runs are an explicit V2+ concern that would require a
	// per-correlation handler map on the broker side.
	r.mu.Lock()
	broker := r.permissionBroker
	r.mu.Unlock()
	if broker != nil {
		// V1.3 reviewer H1 fix: CAS-claim the broker's handler slot.
		// Two concurrent Runs (different SessionIDs OR a same-SessionID
		// retry during the cancel→exit→register handoff window) would
		// otherwise silently overwrite each other's closures, misrouting
		// permission_request envelopes with the wrong correlation_id.
		// Fail loud instead.
		runSessionID := req.SessionID
		ownerToken := runSessionID
		if !r.permHandlerOwner.CompareAndSwap(nil, &ownerToken) {
			existing := r.permHandlerOwner.Load()
			existingID := ""
			if existing != nil {
				existingID = *existing
			}
			r.logger.Warn("runner: permission handler slot busy",
				"existing_owner", existingID,
				"requested_session_id", runSessionID,
			)
			return ErrRunnerBusy
		}
		broker.SetRequestHandler(func(ev protocol.EventSessionPermissionRequest) {
			if err := sink.OnPermissionRequest(ev); err != nil {
				r.logger.Warn("permission_request egress failed",
					"err", err,
					"request_id", ev.RequestID,
					"session_id", ev.SessionID,
					"run_session_id", runSessionID,
				)
			}
		})
		defer func() {
			broker.SetRequestHandler(nil)
			r.permHandlerOwner.Store(nil)
		}()
	}

	args := r.buildArgs(req, settingsPath)
	cmd := execCmd(runCtx, r.cfg.ClaudeBinary, args...)
	cmd.Dir = r.resolveProjectDir(req)
	cmd.Env = r.buildEnv(req)

	// claude.subprocess.start: span around the start phase only (a few ms,
	// covering pipe wiring through cmd.Start()). The parse phase has its own
	// claude.parser.parse span (opened inside Parser.Parse), and the wait
	// phase is implicit between parser.End() and cmd.Wait(). These are
	// intentionally sibling spans — the parser additionally opens per-event
	// child spans (see Parser.dispatchEvent) which carry the bulk of the
	// per-event detail.
	tracer := otel.Tracer(claudeTracerName)
	ctxStart, startSpan := tracer.Start(runCtx, "claude.subprocess.start",
		trace.WithAttributes(
			attribute.String("claude.binary", r.cfg.ClaudeBinary),
			attribute.String("claude.session_id", req.SessionID),
			attribute.String("claude.user_id", req.UserID),
			attribute.String("claude.permission_mode", req.PermissionMode),
			attribute.Int("claude.args_count", len(args)),
		),
	)
	_ = ctxStart // currently unused; kept so future child spans can chain off it.

	stdout, err := cmd.StdoutPipe()
	if err != nil {
		startSpan.RecordError(err)
		startSpan.SetStatus(codes.Error, "stdout pipe failed")
		startSpan.End()
		return fmt.Errorf("claude: stdout pipe: %w", err)
	}
	stderr, err := cmd.StderrPipe()
	if err != nil {
		startSpan.RecordError(err)
		startSpan.SetStatus(codes.Error, "stderr pipe failed")
		startSpan.End()
		return fmt.Errorf("claude: stderr pipe: %w", err)
	}

	if err := cmd.Start(); err != nil {
		startSpan.RecordError(err)
		startSpan.SetStatus(codes.Error, "subprocess start failed")
		startSpan.End()
		return fmt.Errorf("claude: subprocess start: %w", err)
	}
	startSpan.End()

	r.logger.Info("claude subprocess started",
		"session_id", req.SessionID,
		"user_id", req.UserID,
		"binary", r.cfg.ClaudeBinary,
		"cwd", cmd.Dir,
	)

	// Drain stderr concurrently so a chatty subprocess never blocks on a
	// full pipe buffer. The goroutine returns when stderr is closed at
	// process exit.
	stderrDone := make(chan struct{})
	go func() {
		defer close(stderrDone)
		r.drainStderr(stderr)
	}()

	parser := NewParser(sink, r.logger)
	// Wrap parser.Parse in a span so traces clearly show the
	// stream-json consumption phase as a sibling of subprocess.start.
	// Per-event spans live inside Parser.dispatchEvent.
	parseCtx, parseSpan := tracer.Start(runCtx, "claude.parser.parse",
		trace.WithAttributes(attribute.String("claude.session_id", req.SessionID)),
	)
	parser.SetTraceContext(parseCtx)
	parseErr := parser.Parse(stdout)
	if parseErr != nil {
		parseSpan.RecordError(parseErr)
		parseSpan.SetStatus(codes.Error, "stream-json parse failed")
	}
	parseSpan.End()

	waitErr := cmd.Wait()
	<-stderrDone

	if parseErr != nil {
		return fmt.Errorf("claude: parse: %w", parseErr)
	}
	if waitErr != nil {
		// Surface context cancellation as-is so callers can distinguish
		// abort from a real subprocess failure.
		if ctxErr := runCtx.Err(); ctxErr != nil && errors.Is(ctxErr, context.Canceled) {
			return ctxErr
		}
		return fmt.Errorf("claude: subprocess wait: %w", waitErr)
	}
	return nil
}

// buildArgs assembles the claude CLI argument vector per Doc 11 §5. The
// prompt is always the trailing positional argument so flags never collide.
//
// settingsPath, when non-empty, is appended as a "--settings <path>"
// arg pair so the V1.2 per-session overlay (PreToolUse hook
// registration) is loaded by claude. We pass the file path verbatim
// — claude CLI accepts either a path or a JSON literal but the path
// form keeps the argv vector short.
func (r *Runner) buildArgs(req RunRequest, settingsPath string) []string {
	args := []string{
		"-p",
		"--output-format", "stream-json",
		"--verbose",
		"--include-partial-messages",
	}
	permMode := req.PermissionMode
	if permMode == "" {
		permMode = r.cfg.PermissionMode
	}
	if permMode != "" {
		args = append(args, "--permission-mode", permMode)
	}
	if req.SessionID != "" {
		args = append(args, "--resume", req.SessionID)
	}
	if settingsPath != "" {
		args = append(args, "--settings", settingsPath)
	}
	args = append(args, req.Prompt)
	return args
}

// resolveProjectDir picks the per-request override when set, otherwise
// the configured default. An empty string means "inherit current cwd",
// which is acceptable for tests but unusual in production.
func (r *Runner) resolveProjectDir(req RunRequest) string {
	if req.ProjectDir != "" {
		return req.ProjectDir
	}
	return r.cfg.ProjectDir
}

// buildEnv constructs the subprocess environment by stripping
// ANTHROPIC_API_KEY (forces the claude CLI to use Max-subscription auth)
// and conditionally injecting CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1
// when either the request or config opts in.
//
// V1.2 also injects RAFRAF_BRIDGE_PERM_SOCK when the runner has a
// permission broker configured via SetPermissionContext. The
// PreToolUse hook reads this variable to find the bridge UDS — leaving
// it unset is the hook's fail-safe deny path so a misconfigured
// runner never silently routes around the user.
func (r *Runner) buildEnv(req RunRequest) []string {
	env := filterEnv(os.Environ(), "ANTHROPIC_API_KEY")
	if req.AgentTeams || r.cfg.AgentTeams {
		env = append(env, "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1")
	}
	r.mu.Lock()
	sock := r.permissionSockPath
	r.mu.Unlock()
	if sock != "" {
		env = filterEnv(env, "RAFRAF_BRIDGE_PERM_SOCK")
		env = append(env, "RAFRAF_BRIDGE_PERM_SOCK="+sock)
		// V1.4-followup: pipe the operator-configured
		// permission_timeout (broker's per-request ceiling) into
		// the hook so the hook's UDS deadline tracks the broker
		// in lockstep. The hook adds its own +10s grace on top so
		// it never EOFs before the broker decides; we only emit
		// the env var when cfg.PermissionTimeout is positive (zero
		// → omit, hook falls back to its own 190s default —
		// backwards-compatible with V1.0/V1.1 callers passing a
		// zero-value cfg).
		if r.cfg.PermissionTimeout > 0 {
			env = filterEnv(env, "RAFRAF_BRIDGE_PERM_TIMEOUT_MS")
			ms := strconv.FormatInt(int64(r.cfg.PermissionTimeout/time.Millisecond), 10)
			env = append(env, "RAFRAF_BRIDGE_PERM_TIMEOUT_MS="+ms)
		}
	}
	return env
}

// preparePermissionOverlay generates a per-session settings file that
// registers the rafraf-perm-hook binary as a PreToolUse hook. The
// returned cleanup function removes the file (best-effort — a
// crash-killed bridge will leave the file on disk for the next-start
// sweep).
//
// Returns ("", noop) when the runner has no permission context
// configured OR when the hook binary is missing on disk. In the
// latter case we log a warning so the dev workflow surfaces the
// issue instead of silently shipping an unprotected session.
//
// The overlay's hook entry stamps the claude CLI's PreToolUse
// `timeout` field at cfg.PermissionTimeout + 10s grace (same grace
// the rafraf-perm-hook applies to its own UDS deadline) so claude
// doesn't kill the hook before the broker decides. When cfg is nil
// (test scaffolding) OR cfg.PermissionTimeout is zero, the field is
// omitted and claude CLI applies its own 60s default — backwards-
// compatible with V1.0/V1.1 tests.
func (r *Runner) preparePermissionOverlay(req RunRequest) (string, func()) {
	noop := func() {}
	r.mu.Lock()
	sock := r.permissionSockPath
	hook := r.permissionHookPath
	r.mu.Unlock()
	if sock == "" || hook == "" {
		return "", noop
	}
	if _, err := os.Stat(hook); err != nil {
		r.logger.Warn("permission overlay: hook binary missing; skipping --settings injection",
			"err", err,
			"hook", hook,
		)
		return "", noop
	}

	// File name uses the sessionID when known so a process listing
	// can map a file to a live session; falls back to a fresh UUID
	// for the first run of a brand-new session.
	name := req.SessionID
	if name == "" {
		name = randomFileToken()
	}
	path := filepath.Join(os.TempDir(), "rafraf-bridge-settings-"+name+".json")

	body := buildSettingsOverlay(hook, r.claudeHookTimeout())
	if err := os.WriteFile(path, body, 0o600); err != nil {
		r.logger.Warn("permission overlay: write failed; skipping --settings injection",
			"err", err,
			"path", path,
		)
		return "", noop
	}
	cleanup := func() {
		if rerr := os.Remove(path); rerr != nil && !errors.Is(rerr, fs.ErrNotExist) {
			r.logger.Debug("permission overlay: cleanup failed",
				"err", rerr,
				"path", path,
			)
		}
	}
	return path, cleanup
}

// claudeHookTimeoutGrace is the slack added on top of
// cfg.PermissionTimeout when stamping the claude CLI's PreToolUse
// `timeout` field. Mirrors rafraf-perm-hook's own timeoutGrace (10s)
// so the three-layer hierarchy (broker timer < hook UDS deadline <
// claude CLI hook timeout) stays consistent end-to-end without any
// of the layers racing each other.
const claudeHookTimeoutGrace = 10 * time.Second

// claudeHookTimeout returns the duration to stamp onto the claude
// CLI's PreToolUse hook `timeout` field. Returns 0 (→ omit from the
// overlay) when no PermissionTimeout is configured so test scaffolding
// that builds a Runner with a zero-value cfg keeps working.
//
// Centralised so buildEnv (env-var injection) and
// buildSettingsOverlay (settings overlay) share the same source of
// truth — drift between the two would mean either claude kills the
// hook early OR the hook's own UDS deadline expires before claude's
// kill timer, both of which would re-introduce the V1.4-fix race
// from the other side.
func (r *Runner) claudeHookTimeout() time.Duration {
	if r.cfg == nil || r.cfg.PermissionTimeout <= 0 {
		return 0
	}
	return r.cfg.PermissionTimeout + claudeHookTimeoutGrace
}

// buildSettingsOverlay produces the JSON body for the per-session
// settings file. Only the hooks.PreToolUse block is populated so the
// overlay does not clobber any user-installed defaults at merge time
// (claude CLI deep-merges --settings on top of the regular settings
// hierarchy).
//
// hookTimeout, when > 0, is stamped onto the hook entry as
// `timeout` (claude CLI takes seconds, integer). The CLI's own
// PreToolUse hook timeout defaults to 60s; we raise it to match the
// broker's effective ceiling + grace so claude doesn't kill the
// hook before the broker decides. Zero / negative values omit the
// field entirely (claude CLI then applies its own default), which
// preserves backwards compatibility for tests and dev workflows that
// don't care about the long-tail timing.
//
// The grace addition mirrors the rafraf-perm-hook's own
// timeoutGrace (10s) so the layering stays consistent end-to-end:
// broker (T) < hook UDS deadline (T + 10s) < claude CLI hook
// timeout (T + 10s ceiling here too).
func buildSettingsOverlay(hookPath string, hookTimeout time.Duration) []byte {
	type hookCmd struct {
		Type    string `json:"type"`
		Command string `json:"command"`
		// Timeout is integer seconds per the claude CLI hooks
		// documentation. omitempty so the wire format stays
		// minimal when the runner has no timeout context (e.g.
		// older tests that call buildSettingsOverlay directly with
		// a zero duration).
		Timeout int `json:"timeout,omitempty"`
	}
	type matcher struct {
		Matcher string    `json:"matcher"`
		Hooks   []hookCmd `json:"hooks"`
	}
	type hooks struct {
		PreToolUse []matcher `json:"PreToolUse"`
	}
	type root struct {
		Hooks hooks `json:"hooks"`
	}
	cmd := hookCmd{
		Type:    "command",
		Command: hookPath,
	}
	if hookTimeout > 0 {
		// Round up to the next whole second so a sub-second config
		// (vanishingly unlikely in practice but possible from a
		// dev-mode override) doesn't accidentally produce 0.
		secs := int((hookTimeout + time.Second - 1) / time.Second)
		if secs > 0 {
			cmd.Timeout = secs
		}
	}
	body, _ := json.Marshal(root{
		Hooks: hooks{
			PreToolUse: []matcher{{
				Matcher: ".*",
				Hooks:   []hookCmd{cmd},
			}},
		},
	})
	return body
}

// randomFileToken returns a short opaque token used in the settings
// file name when the run has no SessionID yet. We avoid pulling in
// uuid here because the runner package is otherwise zero-dep on
// google/uuid; time.Now() with PID gives us enough entropy for a
// per-process per-spawn unique filename.
func randomFileToken() string {
	return strconv.FormatInt(time.Now().UnixNano(), 36) + "-" + strconv.Itoa(os.Getpid())
}

// filterEnv returns env minus any entry whose key matches removeKey. The
// match is on the literal "KEY=" prefix so values containing "=" are
// preserved as-is.
func filterEnv(env []string, removeKey string) []string {
	prefix := removeKey + "="
	out := make([]string, 0, len(env))
	for _, e := range env {
		if !strings.HasPrefix(e, prefix) {
			out = append(out, e)
		}
	}
	return out
}

// drainStderr reads stderr in chunks and routes each chunk to the runner
// logger at debug level. Returns when the pipe is closed by the
// subprocess exiting.
func (r *Runner) drainStderr(stderr io.Reader) {
	buf := make([]byte, stderrDrainBufSize)
	for {
		n, err := stderr.Read(buf)
		if n > 0 {
			r.logger.Debug("claude stderr", "data", string(buf[:n]))
		}
		if err != nil {
			if !errors.Is(err, io.EOF) {
				r.logger.Debug("claude stderr drain finished", "err", err)
			}
			return
		}
	}
}

// Abort cancels the run identified by sessionID. The subprocess is
// terminated cooperatively via context cancellation; exec.CommandContext
// sends SIGKILL after the underlying os.Process finishes. A short grace
// window lets the subprocess flush before Abort returns.
func (r *Runner) Abort(sessionID string) error {
	r.mu.Lock()
	cur, ok := r.activeRuns[sessionID]
	r.mu.Unlock()
	if !ok {
		return fmt.Errorf("claude: no active run for session %q", sessionID)
	}
	cur.cancel()
	r.logger.Info("claude subprocess abort signalled", "session_id", sessionID)
	time.Sleep(abortGracePeriod)
	return nil
}

// registerActive stores the cancel func keyed by sessionID and returns a
// monotonically-increasing generation token. If a previous run with the
// same sessionID is still mapped, it is cancelled before being overwritten
// so we never leak a goroutine. The returned gen must be supplied to
// unregisterActive so a stale defer cannot delete a newer entry — this
// is the T0.5.5 reviewer M1 fix that survives same-SessionID concurrent
// runs (Run A's defer no longer kills Run B's mapping).
func (r *Runner) registerActive(sessionID string, cancel context.CancelFunc) uint64 {
	r.mu.Lock()
	defer r.mu.Unlock()
	if prev, exists := r.activeRuns[sessionID]; exists {
		prev.cancel()
	}
	r.nextGen++
	gen := r.nextGen
	r.activeRuns[sessionID] = activeRun{cancel: cancel, gen: gen}
	return gen
}

// unregisterActive removes the entry for sessionID iff the stored
// generation matches gen. Compare-and-delete prevents a deferred
// unregister from a now-superseded run from clobbering the newer entry.
func (r *Runner) unregisterActive(sessionID string, gen uint64) {
	r.mu.Lock()
	defer r.mu.Unlock()
	if cur, ok := r.activeRuns[sessionID]; ok && cur.gen == gen {
		delete(r.activeRuns, sessionID)
	}
}

// AuthCheck verifies the local claude CLI is logged in by parsing
// `claude auth status` JSON output. Used at bridge startup per
// Doc 11 §5; a failure indicates either missing authentication or a
// missing claude binary, both of which the caller should surface as
// event.bridge.auth_expired.
func (r *Runner) AuthCheck(ctx context.Context) error {
	cmd := exec.CommandContext(ctx, r.cfg.ClaudeBinary, "auth", "status")
	out, err := cmd.Output()
	if err != nil {
		return fmt.Errorf("claude: auth status invocation failed: %w", err)
	}
	// Tolerate either compact or pretty-printed JSON without taking on a
	// full json.Unmarshal — the loggedIn boolean is the only field we need.
	s := string(out)
	if !strings.Contains(s, `"loggedIn": true`) && !strings.Contains(s, `"loggedIn":true`) {
		return errors.New("claude: not logged in (loggedIn:false)")
	}
	return nil
}
