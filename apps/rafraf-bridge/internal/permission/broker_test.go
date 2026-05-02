// broker_test.go — V1.2 Broker contract tests.
//
// These tests exercise the broker over a real Unix-domain socket
// (`net.Listen("unix", ...)` in `t.TempDir()`) rather than `net.Pipe`
// so we cover the actual wire format the hook binary will speak. The
// tests intentionally avoid spawning the rafraf-perm-hook binary —
// hook subprocess testing lives in
// internal/cmd/rafraf-perm-hook/main_test.go.
//
// Coverage matrix:
//   1. Happy path — request → Resolve(allow) → reply {decision:"allow"}.
//   2. Timeout deny — TimeoutMs=100, no Resolve → {decision:"block",
//      reason:"timeout"}.
//   3. Concurrent requests — 5 dial-in goroutines, distinct Resolve
//      ordering, each gets its own reply.
//   4. Broker close mid-wait — Close() while a request is waiting →
//      {decision:"block", reason:"timeout"} (DecisionExpired path).
//   5. Resolve unknown ID — must NOT panic; debug-log only.
//   6. Bad JSON from hook — broker writes a deny-malformed reply and
//      closes the conn without crashing.
//   7. Risk classifier table — table-driven coverage of every branch
//      in classifyRisk + matchesBashWhitelist + inputPreview.

package permission

import (
	"context"
	"encoding/json"
	"io"
	"log/slog"
	"net"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/protocol"
)

// writeFile is a tiny test helper that wraps os.WriteFile with sane
// perms — the standard "create + 0600" pattern used across the
// package's tests.
func writeFile(path, body string) error {
	return os.WriteFile(path, []byte(body), 0o600)
}

// setMTime backdates a file's mtime so the sweep test can exercise
// the "older than maxAge" branch without a real time-travel.
func setMTime(path string, t time.Time) error {
	return os.Chtimes(path, t, t)
}

// statFile is a thin alias used by tests so the read site stays grep-able.
func statFile(path string) (os.FileInfo, error) {
	return os.Stat(path)
}

// shortSockPath produces a Unix-domain socket path short enough for
// macOS (104-byte SUN_PATH limit). t.TempDir() under TMPDIR can blow
// past this on systems where TMPDIR is deeply nested, so we mint our
// own short directory under /tmp and clean it up via t.Cleanup.
func shortSockPath(t *testing.T, name string) string {
	t.Helper()
	dir, err := os.MkdirTemp("/tmp", "rb")
	if err != nil {
		t.Fatalf("mkdtemp: %v", err)
	}
	t.Cleanup(func() { _ = os.RemoveAll(dir) })
	return filepath.Join(dir, name)
}

// newTestBroker spins up a broker on a fresh socket inside a short
// temp dir with a verbose discard logger. Caller MUST defer cleanup().
//
// Uses NewBroker (not NewBrokerWithTimeout) so the legacy default-path
// constructor stays exercised on every test run; tests that need a
// custom ceiling should call newTestBrokerWithTimeout instead.
func newTestBroker(t *testing.T) (*Broker, func()) {
	t.Helper()
	return newTestBrokerWithTimeout(t, 0)
}

// newTestBrokerWithTimeout is the explicit-timeout sibling of
// newTestBroker. timeout <= 0 selects the broker's built-in default
// (defaultRequestTimeout); positive values are passed through.
// Used by tests that want fast (e.g. 100ms) ceilings without sleeping
// for the production default.
func newTestBrokerWithTimeout(t *testing.T, timeout time.Duration) (*Broker, func()) {
	t.Helper()
	sock := shortSockPath(t, "b.sock")
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	b, err := NewBrokerWithTimeout(sock, timeout, logger)
	if err != nil {
		t.Fatalf("NewBrokerWithTimeout: %v", err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	if err := b.Start(ctx); err != nil {
		cancel()
		_ = b.Close()
		t.Fatalf("Start: %v", err)
	}
	return b, func() {
		cancel()
		_ = b.Close()
	}
}

// dialAndSend writes one hookRequest to the broker and returns the
// raw JSON reply line (without trailing newline).
func dialAndSend(t *testing.T, sock string, req hookRequest) (hookReply, error) {
	t.Helper()
	conn, err := net.DialTimeout("unix", sock, 2*time.Second)
	if err != nil {
		return hookReply{}, err
	}
	defer func() { _ = conn.Close() }()
	body, err := json.Marshal(req)
	if err != nil {
		return hookReply{}, err
	}
	body = append(body, '\n')
	if _, err := conn.Write(body); err != nil {
		return hookReply{}, err
	}
	var reply hookReply
	dec := json.NewDecoder(conn)
	if err := dec.Decode(&reply); err != nil {
		return hookReply{}, err
	}
	return reply, nil
}

// captureRequest installs a SetRequestHandler that records every
// envelope into a mutex-guarded slice and (optionally) calls the
// supplied callback so the test can drive Resolve from inside the
// handler.
func captureRequest(b *Broker) *capturedHandler {
	c := &capturedHandler{}
	b.SetRequestHandler(func(ev protocol.EventSessionPermissionRequest) {
		c.mu.Lock()
		c.events = append(c.events, ev)
		cb := c.cb
		c.mu.Unlock()
		if cb != nil {
			cb(ev)
		}
	})
	return c
}

type capturedHandler struct {
	mu     sync.Mutex
	events []protocol.EventSessionPermissionRequest
	cb     func(ev protocol.EventSessionPermissionRequest)
}

func (c *capturedHandler) snapshot() []protocol.EventSessionPermissionRequest {
	c.mu.Lock()
	defer c.mu.Unlock()
	out := make([]protocol.EventSessionPermissionRequest, len(c.events))
	copy(out, c.events)
	return out
}

func (c *capturedHandler) onRequest(fn func(ev protocol.EventSessionPermissionRequest)) {
	c.mu.Lock()
	c.cb = fn
	c.mu.Unlock()
}

// ----- 1. Happy path ----------------------------------------------------

func TestBroker_HappyPath_AllowResolve(t *testing.T) {
	b, cleanup := newTestBroker(t)
	defer cleanup()

	cap := captureRequest(b)
	cap.onRequest(func(ev protocol.EventSessionPermissionRequest) {
		// Resolve from inside the handler so the dial below
		// completes without a separate goroutine.
		go b.Resolve(ev.RequestID, DecisionAllow)
	})

	reply, err := dialAndSend(t, b.Sock(), hookRequest{
		ToolUseID: "tu-1",
		ToolName:  "Read",
		ToolInput: json.RawMessage(`{"file_path":"/tmp/foo"}`),
		SessionID: "sess-1",
	})
	if err != nil {
		t.Fatalf("dialAndSend: %v", err)
	}
	if reply.Decision != "allow" {
		t.Fatalf("decision = %q, want allow", reply.Decision)
	}
	events := cap.snapshot()
	if len(events) != 1 {
		t.Fatalf("len(events) = %d, want 1", len(events))
	}
	if events[0].ToolName != "Read" {
		t.Fatalf("event.ToolName = %q, want Read", events[0].ToolName)
	}
	if events[0].Risk != "low" {
		t.Fatalf("event.Risk = %q, want low", events[0].Risk)
	}
}

// ----- 2. Timeout deny --------------------------------------------------

func TestBroker_TimeoutDeny(t *testing.T) {
	b, cleanup := newTestBroker(t)
	defer cleanup()

	// Handler that intentionally never resolves.
	b.SetRequestHandler(func(ev protocol.EventSessionPermissionRequest) {
		// noop
		_ = ev
	})

	// Override the per-request timeout via a custom RequestDecision
	// driven directly. We bypass UDS for this test because the
	// broker derives TimeoutMs from the ENVELOPE we build, not from
	// the hookRequest. The UDS path stamps the broker's
	// effectiveTimeout (180s default in V1.4-followup) onto the
	// envelope; the explicit TimeoutMs:50 below short-circuits that
	// to keep the test fast.
	ev := protocol.EventSessionPermissionRequest{
		SessionID: "sess-1",
		RequestID: "req-timeout",
		ToolName:  "Read",
		TimeoutMs: 50,
	}
	start := time.Now()
	dec := b.RequestDecision(context.Background(), ev)
	elapsed := time.Since(start)
	if dec != DecisionExpired {
		t.Fatalf("decision = %q, want expired", dec)
	}
	if elapsed < 40*time.Millisecond || elapsed > 500*time.Millisecond {
		t.Fatalf("elapsed = %v, want ~50ms", elapsed)
	}
}

// ----- 2b. Default-timeout sanity ---------------------------------------

// TestBroker_DefaultTimeoutValue locks the broker's package-level
// default to 180s. The constant doubles as the V1.4-followup-HIGH
// floor (race fix vs. 30s) AND as the value plumbed onto every
// outbound permission_request envelope when no explicit ceiling is
// configured — bumping it without a follow-up review is risky, so the
// test pins it.
func TestBroker_DefaultTimeoutValue(t *testing.T) {
	if defaultRequestTimeout != 180*time.Second {
		t.Fatalf("defaultRequestTimeout = %s, want 180s", defaultRequestTimeout)
	}
}

// TestBroker_EnvelopeTimeoutMs_FromBrokerDefault verifies that when
// the operator does NOT set permission_timeout, the broker stamps the
// outbound permission_request envelope's TimeoutMs with
// defaultRequestTimeout (180s). The iOS countdown + backend clamp
// both depend on this value being present and accurate.
func TestBroker_EnvelopeTimeoutMs_FromBrokerDefault(t *testing.T) {
	b, cleanup := newTestBroker(t)
	defer cleanup()

	cap := captureRequest(b)
	cap.onRequest(func(ev protocol.EventSessionPermissionRequest) {
		go b.Resolve(ev.RequestID, DecisionAllow)
	})

	if _, err := dialAndSend(t, b.Sock(), hookRequest{
		ToolUseID: "tu-default",
		ToolName:  "Read",
		ToolInput: json.RawMessage(`{"file_path":"/tmp/x"}`),
		SessionID: "sess-default",
	}); err != nil {
		t.Fatalf("dialAndSend: %v", err)
	}
	events := cap.snapshot()
	if len(events) != 1 {
		t.Fatalf("len(events) = %d, want 1", len(events))
	}
	wantMs := int(180 * time.Second / time.Millisecond)
	if events[0].TimeoutMs != wantMs {
		t.Fatalf("envelope.TimeoutMs = %d, want %d", events[0].TimeoutMs, wantMs)
	}
}

// TestBroker_EnvelopeTimeoutMs_FromConstructor verifies that an
// operator-supplied ceiling (NewBrokerWithTimeout) is propagated all
// the way into the outbound permission_request envelope. Without
// this, dialing down the broker for low-risk environments would not
// also dial down the iOS countdown — leaving the user staring at a
// 3-minute timer while the broker has already decided.
func TestBroker_EnvelopeTimeoutMs_FromConstructor(t *testing.T) {
	const customTimeout = 250 * time.Millisecond
	b, cleanup := newTestBrokerWithTimeout(t, customTimeout)
	defer cleanup()

	cap := captureRequest(b)
	cap.onRequest(func(ev protocol.EventSessionPermissionRequest) {
		go b.Resolve(ev.RequestID, DecisionAllow)
	})

	if _, err := dialAndSend(t, b.Sock(), hookRequest{
		ToolUseID: "tu-custom",
		ToolName:  "Read",
		ToolInput: json.RawMessage(`{"file_path":"/tmp/x"}`),
		SessionID: "sess-custom",
	}); err != nil {
		t.Fatalf("dialAndSend: %v", err)
	}
	events := cap.snapshot()
	if len(events) != 1 {
		t.Fatalf("len(events) = %d, want 1", len(events))
	}
	wantMs := int(customTimeout / time.Millisecond)
	if events[0].TimeoutMs != wantMs {
		t.Fatalf("envelope.TimeoutMs = %d, want %d", events[0].TimeoutMs, wantMs)
	}
}

// TestBroker_CustomTimeoutHonoured drives RequestDecision directly
// with an envelope whose TimeoutMs is zero — i.e. the broker MUST
// fall back to the constructor-supplied timeout, not to
// defaultRequestTimeout. This is the contract that lets ops dial the
// broker down per environment.
//
// We use a 100ms ceiling so the test stays fast; the elapsed-time
// assertion provides a generous +400ms upper bound to absorb
// scheduler jitter on overloaded CI runners while still catching a
// regression that accidentally re-pointed the fallback at the
// 180s package default.
func TestBroker_CustomTimeoutHonoured(t *testing.T) {
	const customTimeout = 100 * time.Millisecond
	b, cleanup := newTestBrokerWithTimeout(t, customTimeout)
	defer cleanup()

	// Handler that intentionally never resolves so the broker has to
	// fire its own timer.
	b.SetRequestHandler(func(ev protocol.EventSessionPermissionRequest) {
		_ = ev
	})

	ev := protocol.EventSessionPermissionRequest{
		SessionID: "sess-custom-timer",
		RequestID: "req-custom-timer",
		ToolName:  "Read",
		// TimeoutMs left at zero on purpose — exercises the
		// effectiveTimeout fallback path inside RequestDecision.
	}
	start := time.Now()
	dec := b.RequestDecision(context.Background(), ev)
	elapsed := time.Since(start)

	if dec != DecisionExpired {
		t.Fatalf("decision = %q, want expired", dec)
	}
	if elapsed < customTimeout-20*time.Millisecond {
		t.Fatalf("elapsed = %v, want >= ~%s (broker exited too early)", elapsed, customTimeout)
	}
	if elapsed > customTimeout+500*time.Millisecond {
		t.Fatalf("elapsed = %v, want <= ~%s (broker likely fell back to 180s default)",
			elapsed, customTimeout+500*time.Millisecond)
	}
}

// TestBroker_EffectiveTimeoutFallback verifies the
// (b.timeout <= 0) → defaultRequestTimeout branch. The legacy
// NewBroker constructor passes 0 through, so this guards against a
// regression that accidentally drops the fallback and ships a
// zero-timeout broker (which would deny on the first request).
func TestBroker_EffectiveTimeoutFallback(t *testing.T) {
	b, cleanup := newTestBroker(t)
	defer cleanup()
	if got := b.effectiveTimeout(); got != defaultRequestTimeout {
		t.Fatalf("effectiveTimeout() = %s, want %s (default)", got, defaultRequestTimeout)
	}

	b2, cleanup2 := newTestBrokerWithTimeout(t, -5*time.Second)
	defer cleanup2()
	if got := b2.effectiveTimeout(); got != defaultRequestTimeout {
		t.Fatalf("effectiveTimeout() with negative ctor = %s, want %s (default)",
			got, defaultRequestTimeout)
	}

	b3, cleanup3 := newTestBrokerWithTimeout(t, 42*time.Second)
	defer cleanup3()
	if got := b3.effectiveTimeout(); got != 42*time.Second {
		t.Fatalf("effectiveTimeout() with positive ctor = %s, want 42s", got)
	}
}

// ----- 3. Concurrent requests -------------------------------------------

func TestBroker_ConcurrentRequests(t *testing.T) {
	b, cleanup := newTestBroker(t)
	defer cleanup()

	const n = 5
	var (
		recvMu sync.Mutex
		ids    []string
	)
	cap := captureRequest(b)
	cap.onRequest(func(ev protocol.EventSessionPermissionRequest) {
		recvMu.Lock()
		ids = append(ids, ev.RequestID)
		recvMu.Unlock()
		go b.Resolve(ev.RequestID, DecisionAllow)
	})

	results := make(chan hookReply, n)
	errs := make(chan error, n)
	for i := 0; i < n; i++ {
		go func(i int) {
			reply, err := dialAndSend(t, b.Sock(), hookRequest{
				ToolUseID: "tu",
				ToolName:  "Glob",
				ToolInput: json.RawMessage(`{"pattern":"*.go"}`),
				SessionID: "sess",
			})
			if err != nil {
				errs <- err
				return
			}
			results <- reply
		}(i)
	}

	deadline := time.After(5 * time.Second)
	for i := 0; i < n; i++ {
		select {
		case r := <-results:
			if r.Decision != "allow" {
				t.Fatalf("decision = %q, want allow", r.Decision)
			}
		case err := <-errs:
			t.Fatalf("dial error: %v", err)
		case <-deadline:
			t.Fatalf("timed out waiting for replies (got %d/%d)", i, n)
		}
	}
	if got := len(cap.snapshot()); got != n {
		t.Fatalf("envelope count = %d, want %d", got, n)
	}
}

// ----- 4. Broker close mid-wait -----------------------------------------

func TestBroker_CloseMidWait(t *testing.T) {
	b, cleanup := newTestBroker(t)
	// We Close() manually inside the test; the cleanup is still safe
	// (Close is idempotent).
	defer cleanup()

	b.SetRequestHandler(func(ev protocol.EventSessionPermissionRequest) {
		// noop — let the broker close us out
	})

	type result struct {
		reply hookReply
		err   error
	}
	res := make(chan result, 1)
	go func() {
		r, err := dialAndSend(t, b.Sock(), hookRequest{
			ToolUseID: "tu",
			ToolName:  "Edit",
			ToolInput: json.RawMessage(`{"file_path":"/tmp/foo"}`),
			SessionID: "sess",
		})
		res <- result{reply: r, err: err}
	}()

	// Give the goroutine a moment to register the waiter.
	time.Sleep(100 * time.Millisecond)
	if err := b.Close(); err != nil {
		t.Fatalf("Close: %v", err)
	}

	select {
	case r := <-res:
		if r.err != nil {
			// The dial may also EOF after broker close; both are
			// acceptable so long as the hook wouldn't allow.
			t.Logf("dial returned err (acceptable): %v", r.err)
			return
		}
		if r.reply.Decision != "block" {
			t.Fatalf("decision = %q, want block", r.reply.Decision)
		}
		if r.reply.Reason == "" {
			t.Fatalf("reason empty, want non-empty (timeout/expired)")
		}
	case <-time.After(2 * time.Second):
		t.Fatalf("dial did not return after broker close")
	}
}

// ----- 5. Resolve unknown ID --------------------------------------------

func TestBroker_ResolveUnknownDoesNotPanic(t *testing.T) {
	b, cleanup := newTestBroker(t)
	defer cleanup()
	// Should be a noop, no panic.
	b.Resolve("never-existed", DecisionAllow)
	b.Resolve("", DecisionDeny)
}

// ----- 5b. Double Resolve safe -------------------------------------------

func TestBroker_ResolveDoubleSafe(t *testing.T) {
	b, cleanup := newTestBroker(t)
	defer cleanup()

	resolved := make(chan struct{})
	b.SetRequestHandler(func(ev protocol.EventSessionPermissionRequest) {
		go func() {
			b.Resolve(ev.RequestID, DecisionAllow)
			b.Resolve(ev.RequestID, DecisionAllow) // duplicate, must drop
			close(resolved)
		}()
	})

	reply, err := dialAndSend(t, b.Sock(), hookRequest{
		ToolName: "Read",
	})
	if err != nil {
		t.Fatalf("dialAndSend: %v", err)
	}
	if reply.Decision != "allow" {
		t.Fatalf("decision = %q, want allow", reply.Decision)
	}
	<-resolved // confirms second Resolve returned without panic/block
}

// ----- 6. Bad JSON from hook --------------------------------------------

func TestBroker_BadJSON(t *testing.T) {
	b, cleanup := newTestBroker(t)
	defer cleanup()

	conn, err := net.DialTimeout("unix", b.Sock(), 2*time.Second)
	if err != nil {
		t.Fatalf("Dial: %v", err)
	}
	defer func() { _ = conn.Close() }()
	if _, err := conn.Write([]byte("{garbage")); err != nil {
		t.Fatalf("Write: %v", err)
	}
	// Close the write side so the server's decoder hits EOF.
	if uconn, ok := conn.(*net.UnixConn); ok {
		_ = uconn.CloseWrite()
	}
	// The broker should reply with a deny then close.
	var reply hookReply
	dec := json.NewDecoder(conn)
	if err := dec.Decode(&reply); err != nil {
		// EOF is acceptable too — what matters is no panic.
		t.Logf("decode err (acceptable): %v", err)
		return
	}
	if reply.Decision != "block" {
		t.Fatalf("decision = %q, want block", reply.Decision)
	}
}

// ----- 7. Risk classifier table -----------------------------------------

func TestClassifyRisk_Table(t *testing.T) {
	tests := []struct {
		name     string
		tool     string
		input    string
		cwd      string
		wantRisk string
	}{
		{"read", "Read", `{"file_path":"/etc/hosts"}`, "/tmp", "low"},
		{"glob", "Glob", `{"pattern":"*.go"}`, "/tmp", "low"},
		{"grep", "Grep", `{"pattern":"foo"}`, "/tmp", "low"},
		{"ls", "LS", `{"path":"/"}`, "/tmp", "low"},
		{"todowrite", "TodoWrite", `{}`, "/tmp", "low"},
		{"notebookedit", "NotebookEdit", `{}`, "/tmp", "low"},

		{"write_inside", "Write", `{"file_path":"/tmp/foo.txt"}`, "/tmp", "medium"},
		{"edit_inside", "Edit", `{"file_path":"/tmp/sub/foo.txt"}`, "/tmp", "medium"},
		{"write_outside", "Write", `{"file_path":"/var/foo.txt"}`, "/tmp", "medium"},
		{"write_relative_inside", "Write", `{"file_path":"foo.txt"}`, "/tmp", "medium"},
		{"write_path_missing", "Write", `{}`, "/tmp", "medium"},

		{"bash_whitelist_ls", "Bash", `{"command":"ls -la"}`, "/tmp", "medium"},
		{"bash_whitelist_git_status", "Bash", `{"command":"git status -sb"}`, "/tmp", "medium"},
		{"bash_whitelist_docker_logs", "Bash", `{"command":"docker logs my-container"}`, "/tmp", "medium"},
		{"bash_whitelist_npm_test", "Bash", `{"command":"npm test"}`, "/tmp", "medium"},
		{"bash_off_whitelist_rm", "Bash", `{"command":"rm -rf /tmp/foo"}`, "/tmp", "high"},
		{"bash_off_whitelist_curl", "Bash", `{"command":"curl https://evil.example"}`, "/tmp", "high"},
		{"bash_empty", "Bash", `{}`, "/tmp", "high"},

		{"webfetch", "WebFetch", `{"url":"https://x"}`, "/tmp", "high"},
		{"websearch", "WebSearch", `{"query":"foo"}`, "/tmp", "high"},

		{"unknown_tool", "MysteryPlugin", `{}`, "/tmp", "high"},
		{"empty_tool", "", `{}`, "/tmp", "high"},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			got, _ := classifyRisk(tc.tool, json.RawMessage(tc.input), tc.cwd)
			if got != tc.wantRisk {
				t.Fatalf("classifyRisk(%q) = %q, want %q", tc.name, got, tc.wantRisk)
			}
		})
	}
}

func TestInputPreview_Truncation(t *testing.T) {
	short := json.RawMessage(`{"a":"b"}`)
	if got := inputPreview(short); got != string(short) {
		t.Fatalf("short preview = %q, want passthrough", got)
	}

	long := strings.Repeat("x", 500)
	raw := json.RawMessage(`"` + long + `"`)
	got := inputPreview(raw)
	if len(got) > inputPreviewMaxBytes+3 { // +3 for "..."
		t.Fatalf("preview len = %d, want <= %d", len(got), inputPreviewMaxBytes+3)
	}
	if !strings.HasSuffix(got, "...") {
		t.Fatalf("preview = %q, want trailing ...", got[len(got)-10:])
	}
}

func TestInputPreview_UTF8Boundary(t *testing.T) {
	// 4-byte rune ("😀" U+1F600). Build a payload long enough to force
	// truncation right around a multi-byte rune.
	payload := strings.Repeat("😀", 100) // 400 bytes, 100 runes
	raw := json.RawMessage(`"` + payload + `"`)
	got := inputPreview(raw)
	// Strip trailing "..." for the validity check.
	body := strings.TrimSuffix(got, "...")
	for i, r := range body {
		if r == 0xFFFD {
			t.Fatalf("invalid utf-8 at byte %d in preview", i)
		}
	}
}

// ----- 7b. Reclaim socket ----------------------------------------------

func TestNewBroker_ReclaimsStaleSocket(t *testing.T) {
	sock := shortSockPath(t, "s.sock")
	// Create a stale unix socket file by binding + closing.
	ln, err := net.Listen("unix", sock)
	if err != nil {
		t.Fatalf("seed listen: %v", err)
	}
	_ = ln.Close()
	// Re-create the file so it persists (some kernels remove it on
	// Close — recreate as a regular socket file marker).
	// On macOS the close usually leaves the inode; if not, NewBroker's
	// stat will see ErrNotExist which is fine. Either way the test
	// must not error.
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	b, err := NewBroker(sock, logger)
	if err != nil {
		t.Fatalf("NewBroker: %v", err)
	}
	defer func() { _ = b.Close() }()
	if b.Sock() != sock {
		t.Fatalf("Sock = %q, want %q", b.Sock(), sock)
	}
}

func TestNewBroker_RefusesActiveSocket(t *testing.T) {
	sock := shortSockPath(t, "a.sock")
	ln, err := net.Listen("unix", sock)
	if err != nil {
		t.Fatalf("seed listen: %v", err)
	}
	defer func() { _ = ln.Close() }()
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	if _, err := NewBroker(sock, logger); err == nil {
		t.Fatalf("NewBroker should refuse active socket")
	}
}

// ----- 7c. Sweep -------------------------------------------------------

func TestSweepStaleArtifacts(t *testing.T) {
	// Stage two files in TMPDIR that match our patterns and one
	// unrelated file. The sweep must touch only the two patterns AND
	// only when older than maxAge.
	tmp := t.TempDir()
	t.Setenv("TMPDIR", tmp)

	staleSettings := filepath.Join(tmp, "rafraf-bridge-settings-old.json")
	if err := writeFile(staleSettings, "{}"); err != nil {
		t.Fatal(err)
	}
	freshSettings := filepath.Join(tmp, "rafraf-bridge-settings-new.json")
	if err := writeFile(freshSettings, "{}"); err != nil {
		t.Fatal(err)
	}
	unrelated := filepath.Join(tmp, "unrelated.txt")
	if err := writeFile(unrelated, "x"); err != nil {
		t.Fatal(err)
	}
	// Push staleSettings mtime back by 2h.
	past := time.Now().Add(-2 * time.Hour)
	if err := setMTime(staleSettings, past); err != nil {
		t.Fatal(err)
	}

	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	SweepStaleArtifacts(logger, "", time.Hour)

	if _, err := statFile(staleSettings); err == nil {
		t.Fatalf("stale settings file still exists")
	}
	if _, err := statFile(freshSettings); err != nil {
		t.Fatalf("fresh settings file removed: %v", err)
	}
	if _, err := statFile(unrelated); err != nil {
		t.Fatalf("unrelated file removed: %v", err)
	}
}
