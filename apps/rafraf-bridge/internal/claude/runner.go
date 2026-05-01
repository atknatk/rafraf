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
	"errors"
	"fmt"
	"io"
	"log/slog"
	"os"
	"os/exec"
	"strings"
	"sync"
	"time"

	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/config"
	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/protocol"
	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/telemetry"
)

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
type Runner struct {
	cfg    *config.Config
	logger *slog.Logger

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

	args := r.buildArgs(req)
	cmd := execCmd(runCtx, r.cfg.ClaudeBinary, args...)
	cmd.Dir = r.resolveProjectDir(req)
	cmd.Env = r.buildEnv(req)

	stdout, err := cmd.StdoutPipe()
	if err != nil {
		return fmt.Errorf("claude: stdout pipe: %w", err)
	}
	stderr, err := cmd.StderrPipe()
	if err != nil {
		return fmt.Errorf("claude: stderr pipe: %w", err)
	}

	if err := cmd.Start(); err != nil {
		return fmt.Errorf("claude: subprocess start: %w", err)
	}

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
	parseErr := parser.Parse(stdout)

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
func (r *Runner) buildArgs(req RunRequest) []string {
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
func (r *Runner) buildEnv(req RunRequest) []string {
	env := filterEnv(os.Environ(), "ANTHROPIC_API_KEY")
	if req.AgentTeams || r.cfg.AgentTeams {
		env = append(env, "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1")
	}
	return env
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
