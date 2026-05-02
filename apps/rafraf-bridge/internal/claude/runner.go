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

	mu         sync.Mutex
	activeRuns map[string]activeRun // sessionID → cancel + generation
	nextGen    uint64               // monotonic, advanced under mu
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
}

// ExecCommandFn matches exec.CommandContext's signature so tests can
// substitute a stub that emits canned stream-json from a fixture file.
type ExecCommandFn func(ctx context.Context, name string, args ...string) *exec.Cmd

// NewRunner constructs a Runner. logger may be nil; a no-op default is
// substituted in that case so call sites need not check.
//
// V1.2 callers should follow up with SetPermissionContext(sock, hook)
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

// SetPermissionContext configures the V1.2 PreToolUse hook injection.
// sockPath is the broker UDS the hook will dial; hookPath is the
// absolute path to the rafraf-perm-hook binary. Either being empty
// disables injection (the runner logs a warning at first Run() and
// proceeds without --settings).
//
// The runner stores both paths verbatim — it does NOT validate that
// hookPath exists at SetPermissionContext-time so callers can wire
// the deferred hook discovery (typical: bridge startup hits this with
// the path it just resolved via os.Executable() sibling lookup).
func (r *Runner) SetPermissionContext(sockPath, hookPath string) {
	r.mu.Lock()
	defer r.mu.Unlock()
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

	body := buildSettingsOverlay(hook)
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

// buildSettingsOverlay produces the JSON body for the per-session
// settings file. Only the hooks.PreToolUse block is populated so the
// overlay does not clobber any user-installed defaults at merge time
// (claude CLI deep-merges --settings on top of the regular settings
// hierarchy).
func buildSettingsOverlay(hookPath string) []byte {
	type hookCmd struct {
		Type    string `json:"type"`
		Command string `json:"command"`
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
	body, _ := json.Marshal(root{
		Hooks: hooks{
			PreToolUse: []matcher{{
				Matcher: ".*",
				Hooks: []hookCmd{{
					Type:    "command",
					Command: hookPath,
				}},
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
