package claude

import (
	"context"
	"errors"
	"io"
	"log/slog"
	"os"
	"os/exec"
	"path/filepath"
	"slices"
	"strings"
	"testing"
	"time"

	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/config"
	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/protocol"
	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/telemetry"
)

// silentLogger returns a slog.Logger that discards every record so test
// output stays focused on the t.Log/t.Errorf surface.
func silentLogger() *slog.Logger {
	return slog.New(slog.NewTextHandler(io.Discard, nil))
}

// nullSink is an EventSink whose every method is a no-op success. The
// T0.5.5 placeholder Parser does not invoke the sink, but having a
// concrete type lets tests construct Runner.Run calls without a panic
// risk if the implementation evolves.
type nullSink struct{}

func (nullSink) OnInit(protocol.EventSessionInit) error                 { return nil }
func (nullSink) OnAssistant(protocol.EventSessionAssistant) error       { return nil }
func (nullSink) OnUser(protocol.EventSessionUser) error                 { return nil }
func (nullSink) OnStream(protocol.EventSessionStream) error             { return nil }
func (nullSink) OnTaskStarted(protocol.EventSessionTaskStarted) error   { return nil }
func (nullSink) OnTaskProgress(protocol.EventSessionTaskProgress) error { return nil }
func (nullSink) OnTaskNotification(protocol.EventSessionTaskNotification) error {
	return nil
}
func (nullSink) OnRateLimit(protocol.EventSessionRateLimit) error       { return nil }
func (nullSink) OnHookStarted(protocol.EventSessionHookStarted) error   { return nil }
func (nullSink) OnHookResponse(protocol.EventSessionHookResponse) error { return nil }
func (nullSink) OnResult(protocol.EventSessionResult) error             { return nil }
func (nullSink) OnPermissionRequest(protocol.EventSessionPermissionRequest) error {
	return nil
}

// ---------------------------------------------------------------------------
// buildArgs — argument vector composition.
// ---------------------------------------------------------------------------

func TestRunner_BuildArgs_Basic(t *testing.T) {
	t.Parallel()

	cfg := &config.Config{ClaudeBinary: "claude", PermissionMode: "acceptEdits"}
	r := NewRunner(cfg, silentLogger())

	got := r.buildArgs(RunRequest{Prompt: "do the thing"}, "")
	want := []string{
		"-p",
		"--output-format", "stream-json",
		"--verbose",
		"--include-partial-messages",
		"--permission-mode", "acceptEdits",
		"do the thing",
	}
	if !slices.Equal(got, want) {
		t.Fatalf("buildArgs basic:\n got: %#v\nwant: %#v", got, want)
	}
}

func TestRunner_BuildArgs_WithSession(t *testing.T) {
	t.Parallel()

	cfg := &config.Config{ClaudeBinary: "claude", PermissionMode: "default"}
	r := NewRunner(cfg, silentLogger())

	got := r.buildArgs(RunRequest{
		Prompt:    "follow up",
		SessionID: "sess-42",
	}, "")

	// --resume must precede the trailing positional prompt.
	if !slices.Contains(got, "--resume") {
		t.Fatalf("buildArgs: --resume missing, got %#v", got)
	}
	for i, tok := range got {
		if tok == "--resume" {
			if i+1 >= len(got) || got[i+1] != "sess-42" {
				t.Fatalf("buildArgs: --resume not followed by session id, got %#v", got)
			}
		}
	}
	if got[len(got)-1] != "follow up" {
		t.Fatalf("buildArgs: prompt must be trailing positional, got %#v", got)
	}
}

func TestRunner_BuildArgs_PermissionModeOverride(t *testing.T) {
	t.Parallel()

	// Config default is acceptEdits; per-request override must win.
	cfg := &config.Config{ClaudeBinary: "claude", PermissionMode: "acceptEdits"}
	r := NewRunner(cfg, silentLogger())

	got := r.buildArgs(RunRequest{
		Prompt:         "audit",
		PermissionMode: "plan",
	}, "")

	for i, tok := range got {
		if tok == "--permission-mode" {
			if i+1 >= len(got) || got[i+1] != "plan" {
				t.Fatalf("buildArgs: per-request permission mode did not override config, got %#v", got)
			}
			return
		}
	}
	t.Fatalf("buildArgs: --permission-mode missing entirely, got %#v", got)
}

func TestRunner_BuildArgs_OmitsPermissionWhenBlank(t *testing.T) {
	t.Parallel()

	// Config has no permission_mode; request also omits it. The flag
	// should be skipped entirely so claude uses its built-in default.
	cfg := &config.Config{ClaudeBinary: "claude"}
	r := NewRunner(cfg, silentLogger())

	got := r.buildArgs(RunRequest{Prompt: "go"}, "")
	if slices.Contains(got, "--permission-mode") {
		t.Fatalf("buildArgs: --permission-mode must be omitted when blank, got %#v", got)
	}
}

// ---------------------------------------------------------------------------
// V1.2 — settings overlay injection.
// ---------------------------------------------------------------------------

func TestRunner_BuildArgs_AppendsSettingsWhenProvided(t *testing.T) {
	t.Parallel()
	cfg := &config.Config{ClaudeBinary: "claude"}
	r := NewRunner(cfg, silentLogger())
	got := r.buildArgs(RunRequest{Prompt: "p"}, "/tmp/overlay.json")
	// --settings + path must appear and the prompt remains the
	// trailing positional.
	idx := slices.Index(got, "--settings")
	if idx == -1 {
		t.Fatalf("buildArgs: --settings missing, got %#v", got)
	}
	if got[idx+1] != "/tmp/overlay.json" {
		t.Fatalf("buildArgs: --settings not followed by path, got %#v", got)
	}
	if got[len(got)-1] != "p" {
		t.Fatalf("buildArgs: prompt not last, got %#v", got)
	}
}

func TestRunner_BuildEnv_InjectsBrokerSockWhenSet(t *testing.T) {
	t.Parallel()
	r := NewRunner(&config.Config{}, silentLogger())
	// V1.3: nil broker is fine here — this test only exercises buildEnv.
	r.SetPermissionContext(nil, "/tmp/broker.sock", "/usr/local/bin/rafraf-perm-hook")
	env := r.buildEnv(RunRequest{})
	if !slices.Contains(env, "RAFRAF_BRIDGE_PERM_SOCK=/tmp/broker.sock") {
		t.Fatalf("buildEnv: expected RAFRAF_BRIDGE_PERM_SOCK in env, got %#v", env)
	}
}

func TestRunner_BuildEnv_OmitsBrokerSockByDefault(t *testing.T) {
	t.Parallel()
	r := NewRunner(&config.Config{}, silentLogger())
	env := r.buildEnv(RunRequest{})
	for _, e := range env {
		if strings.HasPrefix(e, "RAFRAF_BRIDGE_PERM_SOCK=") {
			t.Fatalf("buildEnv: must not inject RAFRAF_BRIDGE_PERM_SOCK without context, got %q", e)
		}
	}
}

func TestRunner_PreparePermissionOverlay_NoContextSkips(t *testing.T) {
	t.Parallel()
	r := NewRunner(&config.Config{}, silentLogger())
	path, cleanup := r.preparePermissionOverlay(RunRequest{})
	defer cleanup()
	if path != "" {
		t.Fatalf("preparePermissionOverlay: expected empty path, got %q", path)
	}
}

func TestRunner_PreparePermissionOverlay_MissingHookSkips(t *testing.T) {
	t.Parallel()
	r := NewRunner(&config.Config{}, silentLogger())
	r.SetPermissionContext(nil, "/tmp/sock", "/non/existent/hook-binary")
	path, cleanup := r.preparePermissionOverlay(RunRequest{SessionID: "sess"})
	defer cleanup()
	if path != "" {
		t.Fatalf("preparePermissionOverlay: must skip when hook missing, got %q", path)
	}
}

func TestRunner_PreparePermissionOverlay_WritesAndCleans(t *testing.T) {
	t.Parallel()
	// Pretend the hook binary is /bin/sh which always exists.
	hook := "/bin/sh"
	if _, err := os.Stat(hook); err != nil {
		t.Skipf("/bin/sh not present, skipping: %v", err)
	}
	r := NewRunner(&config.Config{}, silentLogger())
	r.SetPermissionContext(nil, "/tmp/sock", hook)
	path, cleanup := r.preparePermissionOverlay(RunRequest{SessionID: "test-sess-123"})
	if path == "" {
		t.Fatalf("preparePermissionOverlay: expected non-empty path")
	}
	body, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read overlay: %v", err)
	}
	if !strings.Contains(string(body), "PreToolUse") {
		t.Fatalf("overlay body missing PreToolUse: %s", body)
	}
	if !strings.Contains(string(body), hook) {
		t.Fatalf("overlay body missing hook path %s: %s", hook, body)
	}
	cleanup()
	if _, err := os.Stat(path); err == nil {
		t.Fatalf("overlay still present after cleanup: %s", path)
	}
}

// ---------------------------------------------------------------------------
// buildEnv — env filtering and feature flag injection.
// ---------------------------------------------------------------------------

func TestRunner_BuildEnv_FiltersAnthropicKey(t *testing.T) {
	// t.Setenv forbids t.Parallel; this test runs serially.
	t.Setenv("ANTHROPIC_API_KEY", "sk-test-leak-canary")
	t.Setenv("HOME", "/tmp/fake-home") // sentinel to ensure other vars survive

	r := NewRunner(&config.Config{}, silentLogger())
	env := r.buildEnv(RunRequest{})

	for _, e := range env {
		if strings.HasPrefix(e, "ANTHROPIC_API_KEY=") {
			t.Fatalf("buildEnv: ANTHROPIC_API_KEY leaked into subprocess env: %q", e)
		}
	}
	// Sanity: HOME (or other unrelated vars) should still be present.
	if !slices.ContainsFunc(env, func(s string) bool { return strings.HasPrefix(s, "HOME=") }) {
		t.Fatalf("buildEnv: dropped unrelated env var HOME, got %d entries", len(env))
	}
}

func TestRunner_BuildEnv_InjectsAgentTeamsFromRequest(t *testing.T) {
	t.Parallel()

	r := NewRunner(&config.Config{}, silentLogger())
	env := r.buildEnv(RunRequest{AgentTeams: true})

	if !slices.Contains(env, "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1") {
		t.Fatalf("buildEnv: expected CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 in env when request opts in")
	}
}

func TestRunner_BuildEnv_InjectsAgentTeamsFromConfig(t *testing.T) {
	t.Parallel()

	r := NewRunner(&config.Config{AgentTeams: true}, silentLogger())
	env := r.buildEnv(RunRequest{})

	if !slices.Contains(env, "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1") {
		t.Fatalf("buildEnv: expected CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 in env when config opts in")
	}
}

func TestRunner_BuildEnv_OmitsAgentTeamsByDefault(t *testing.T) {
	// Cannot use t.Parallel — t.Setenv mutates process state.
	// We assert that buildEnv does not *inject* the flag when neither
	// the request nor config opts in. To make this robust against the
	// developer's own shell having CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1
	// (which the runner intentionally passes through unchanged), we
	// strip it from the parent process env first via t.Setenv to a
	// sentinel and then post-filter it out of buildEnv's result.
	t.Setenv("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", "__sentinel_inherited__")

	r := NewRunner(&config.Config{}, silentLogger())
	env := r.buildEnv(RunRequest{})

	if slices.Contains(env, "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1") {
		t.Fatalf("buildEnv: must not synthesise =1 when neither config nor request opts in")
	}
	// The sentinel value should still pass through unchanged — runner
	// only cares about *injection*, never about scrubbing this key.
	if !slices.Contains(env, "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=__sentinel_inherited__") {
		t.Fatalf("buildEnv: must preserve inherited values for CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS")
	}
}

// ---------------------------------------------------------------------------
// filterEnv — direct unit test for the env-stripping helper.
// ---------------------------------------------------------------------------

func TestFilterEnv_RemovesOnlyExactKey(t *testing.T) {
	t.Parallel()

	in := []string{
		"FOO=1",
		"ANTHROPIC_API_KEY=secret",
		"BAR=hello=world",               // value contains "=" — must survive
		"ANTHROPIC_API_KEY_SUFFIX=keep", // prefix match must NOT match
	}
	out := filterEnv(in, "ANTHROPIC_API_KEY")

	want := []string{
		"FOO=1",
		"BAR=hello=world",
		"ANTHROPIC_API_KEY_SUFFIX=keep",
	}
	if !slices.Equal(out, want) {
		t.Fatalf("filterEnv:\n got: %#v\nwant: %#v", out, want)
	}
}

// ---------------------------------------------------------------------------
// resolveProjectDir — override fallback.
// ---------------------------------------------------------------------------

func TestRunner_ResolveProjectDir_FallsBackToConfig(t *testing.T) {
	t.Parallel()

	cfg := &config.Config{ProjectDir: "/cfg/path"}
	r := NewRunner(cfg, silentLogger())

	if got := r.resolveProjectDir(RunRequest{}); got != "/cfg/path" {
		t.Fatalf("resolveProjectDir: empty request should fall back to config, got %q", got)
	}
	if got := r.resolveProjectDir(RunRequest{ProjectDir: "/req/path"}); got != "/req/path" {
		t.Fatalf("resolveProjectDir: per-request override ignored, got %q", got)
	}
}

// ---------------------------------------------------------------------------
// Run — subprocess mock via `cat testdata/01-simple.jsonl`.
//
// The injected ExecCommandFn rewrites every Runner-built `claude ...` call
// into `cat <fixture>` so we exercise the real pipe + bufio.Scanner +
// telemetry path without depending on the claude binary.
// ---------------------------------------------------------------------------

func TestRunner_Run_WithFixture(t *testing.T) {
	cfg := &config.Config{
		ClaudeBinary:   "claude", // ignored by our exec stub
		PermissionMode: "acceptEdits",
		ProjectDir:     t.TempDir(),
	}
	r := NewRunner(cfg, silentLogger())

	// Resolve the fixture to an absolute path so the cwd override on the
	// stubbed exec.Cmd does not break the cat invocation.
	fixture, err := filepath.Abs(filepath.Join("testdata", "01-simple.jsonl"))
	if err != nil {
		t.Fatalf("resolve fixture path: %v", err)
	}

	before := telemetry.ClaudeLinesRead.Load()
	beforeTotal := telemetry.ClaudeSubprocessTotal.Load()

	stub := func(ctx context.Context, _ string, _ ...string) *exec.Cmd {
		// Replace the entire invocation with a deterministic fixture player.
		return exec.CommandContext(ctx, "cat", fixture)
	}

	if runErr := r.runWithExec(context.Background(), RunRequest{
		Prompt: "irrelevant — fixture is the source",
	}, nullSink{}, stub); runErr != nil {
		t.Fatalf("Run: unexpected error: %v", runErr)
	}

	if got := telemetry.ClaudeLinesRead.Load() - before; got != 3 {
		t.Fatalf("Run: expected fixture to yield 3 lines, telemetry delta = %d", got)
	}
	if got := telemetry.ClaudeSubprocessTotal.Load() - beforeTotal; got != 1 {
		t.Fatalf("Run: ClaudeSubprocessTotal should increment by 1, delta = %d", got)
	}
	if got := telemetry.ClaudeSubprocessActive.Load(); got != 0 {
		t.Fatalf("Run: ClaudeSubprocessActive should return to 0 after exit, got %d", got)
	}
}

// ---------------------------------------------------------------------------
// Abort — long-running subprocess cancelled mid-flight.
//
// Uses `sh -c 'sleep 30'` as a stand-in for a stuck claude invocation.
// Abort() must cause Run to return within ~1s with a context.Canceled
// error rather than the configured 30s sleep elapsing.
// ---------------------------------------------------------------------------

func TestRunner_Abort_TerminatesActiveRun(t *testing.T) {
	cfg := &config.Config{ClaudeBinary: "claude"}
	r := NewRunner(cfg, silentLogger())

	stub := func(ctx context.Context, _ string, _ ...string) *exec.Cmd {
		return exec.CommandContext(ctx, "sh", "-c", "sleep 30")
	}

	const sessionID = "long-runner"
	done := make(chan error, 1)
	go func() {
		done <- r.runWithExec(context.Background(), RunRequest{
			Prompt:    "block",
			SessionID: sessionID,
		}, nullSink{}, stub)
	}()

	// Wait briefly for the run to register itself in the active map.
	deadline := time.Now().Add(500 * time.Millisecond)
	for time.Now().Before(deadline) {
		r.mu.Lock()
		_, present := r.activeRuns[sessionID]
		r.mu.Unlock()
		if present {
			break
		}
		time.Sleep(10 * time.Millisecond)
	}

	if err := r.Abort(sessionID); err != nil {
		t.Fatalf("Abort: unexpected error: %v", err)
	}

	select {
	case err := <-done:
		// Cancellation may surface as context.Canceled, an "exit status",
		// or a "signal: killed" wait error — anything except a clean nil
		// (which would imply the sleep completed) is acceptable.
		if err == nil {
			t.Fatalf("Abort: Run returned nil; expected cancellation error")
		}
		if !errors.Is(err, context.Canceled) && !strings.Contains(err.Error(), "signal") &&
			!strings.Contains(err.Error(), "exit") {
			t.Logf("Abort: returned err = %v (acceptable)", err)
		}
	case <-time.After(3 * time.Second):
		t.Fatalf("Abort: Run did not return within 3s of Abort()")
	}
}

func TestRunner_Abort_UnknownSessionReturnsError(t *testing.T) {
	t.Parallel()

	r := NewRunner(&config.Config{ClaudeBinary: "claude"}, silentLogger())
	if err := r.Abort("does-not-exist"); err == nil {
		t.Fatalf("Abort: expected error for unknown session, got nil")
	}
}

// ---------------------------------------------------------------------------
// activeRuns generation safety — T0.5.5 reviewer M1 fix folded into T0.5.6.
//
// Scenario: Run A registers, Run B registers under the same SessionID
// (which cancels A and replaces the entry). Then A's deferred
// unregisterActive must NOT delete B's entry — Abort(sessionID) must
// still resolve to B's cancel.
// ---------------------------------------------------------------------------

func TestRunner_ConcurrentSameSession_GenSafetyKeepsNewer(t *testing.T) {
	t.Parallel()

	r := NewRunner(&config.Config{ClaudeBinary: "claude"}, silentLogger())
	const sessionID = "shared-session"

	_, cancelA := context.WithCancel(context.Background())
	defer cancelA()
	genA := r.registerActive(sessionID, cancelA)

	// Simulate B taking over the slot — registerActive cancels A and
	// returns a new generation token.
	bCancelled := make(chan struct{}, 1)
	cancelB := func() {
		select {
		case bCancelled <- struct{}{}:
		default:
		}
	}
	genB := r.registerActive(sessionID, cancelB)
	if genA == genB {
		t.Fatalf("expected distinct generations, got A=%d B=%d", genA, genB)
	}

	// A's deferred unregister fires now — it MUST be a no-op because
	// cur.gen == genB, not genA.
	r.unregisterActive(sessionID, genA)

	r.mu.Lock()
	cur, present := r.activeRuns[sessionID]
	r.mu.Unlock()
	if !present {
		t.Fatalf("activeRuns[%q] dropped by stale-gen unregister", sessionID)
	}
	if cur.gen != genB {
		t.Fatalf("activeRuns[%q].gen: want %d (B), got %d", sessionID, genB, cur.gen)
	}

	// Abort must hit B's cancel, not error out.
	if err := r.Abort(sessionID); err != nil {
		t.Fatalf("Abort: unexpected error: %v", err)
	}
	select {
	case <-bCancelled:
	default:
		t.Fatalf("Abort did not invoke B's cancel func")
	}

	// And the matching-gen unregister cleans up.
	r.unregisterActive(sessionID, genB)
	r.mu.Lock()
	_, stillPresent := r.activeRuns[sessionID]
	r.mu.Unlock()
	if stillPresent {
		t.Fatalf("activeRuns[%q] not cleaned up by matching-gen unregister", sessionID)
	}
}

// TestRunner_RegisterActive_CancelsPrevious — sanity check that the
// "second register cancels the first" branch fires; the M1 fix preserves
// this behaviour while also patching the stale-defer race.
func TestRunner_RegisterActive_CancelsPrevious(t *testing.T) {
	t.Parallel()

	r := NewRunner(&config.Config{ClaudeBinary: "claude"}, silentLogger())
	const sessionID = "first-then-second"

	firstCancelled := make(chan struct{}, 1)
	cancelFirst := func() {
		select {
		case firstCancelled <- struct{}{}:
		default:
		}
	}
	r.registerActive(sessionID, cancelFirst)

	_, cancelSecond := context.WithCancel(context.Background())
	defer cancelSecond()
	r.registerActive(sessionID, cancelSecond)

	select {
	case <-firstCancelled:
	default:
		t.Fatalf("registerActive did not cancel the previous holder")
	}
}
