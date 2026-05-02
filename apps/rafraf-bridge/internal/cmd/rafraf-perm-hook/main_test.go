// main_test.go — V1.2 hook binary unit tests.
//
// We exercise `run()` directly (the testable variant) so we can
// inject stdin/stdout/stderr + a fake UDS path. A tiny goroutine
// stands up a one-shot UDS server using `net.Listen("unix", ...)` to
// emulate the bridge's permission.Broker. The path lives under /tmp
// to dodge macOS's 104-byte SUN_PATH limit.
package main

import (
	"bytes"
	"encoding/json"
	"net"
	"os"
	"path/filepath"
	"sync"
	"testing"
	"time"
)

func shortSock(t *testing.T) string {
	t.Helper()
	dir, err := os.MkdirTemp("/tmp", "h")
	if err != nil {
		t.Fatalf("mkdtemp: %v", err)
	}
	t.Cleanup(func() { _ = os.RemoveAll(dir) })
	return filepath.Join(dir, "h.sock")
}

// fakeBroker spins up a UDS listener that decodes one brokerRequest
// per connection and replies with the supplied brokerReply. Returns
// the socket path and a shutdown closure.
func fakeBroker(t *testing.T, reply brokerReply) (string, func()) {
	t.Helper()
	sock := shortSock(t)
	ln, err := net.Listen("unix", sock)
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	done := make(chan struct{})
	var wg sync.WaitGroup
	wg.Add(1)
	go func() {
		defer wg.Done()
		for {
			conn, aerr := ln.Accept()
			if aerr != nil {
				return
			}
			go func(c net.Conn) {
				defer func() { _ = c.Close() }()
				var req brokerRequest
				dec := json.NewDecoder(c)
				if derr := dec.Decode(&req); derr != nil {
					return
				}
				body, _ := json.Marshal(reply)
				body = append(body, '\n')
				_, _ = c.Write(body)
			}(conn)
		}
	}()
	stop := func() {
		_ = ln.Close()
		close(done)
		wg.Wait()
	}
	return sock, stop
}

func mustStdin(t *testing.T, name string) []byte {
	t.Helper()
	in := claudeStdin{
		HookEventName: "PreToolUse",
		ToolName:      name,
		ToolInput:     json.RawMessage(`{"file_path":"/tmp/foo"}`),
		SessionID:     "sess-1",
		ToolUseID:     "tu-1",
	}
	body, err := json.Marshal(in)
	if err != nil {
		t.Fatalf("marshal stdin: %v", err)
	}
	return body
}

func decodeOut(t *testing.T, raw []byte) hookOutput {
	t.Helper()
	var out hookOutput
	if err := json.Unmarshal(bytes.TrimSpace(raw), &out); err != nil {
		t.Fatalf("decode stdout %q: %v", raw, err)
	}
	return out
}

// ----- 1. Happy path — broker says allow ---------------------------------

func TestHook_HappyPathAllow(t *testing.T) {
	sock, stop := fakeBroker(t, brokerReply{Decision: "allow"})
	defer stop()

	stdin := bytes.NewReader(mustStdin(t, "Read"))
	var stdout, stderr bytes.Buffer
	run(stdin, &stdout, &stderr, sock, defaultReadTimeout)

	got := decodeOut(t, stdout.Bytes())
	if got.Decision != "allow" {
		t.Fatalf("decision = %q, want allow (stderr=%q)", got.Decision, stderr.String())
	}
}

// ----- 2. Broker says block ----------------------------------------------

func TestHook_BrokerBlock(t *testing.T) {
	sock, stop := fakeBroker(t, brokerReply{Decision: "block", Reason: "user denied"})
	defer stop()

	stdin := bytes.NewReader(mustStdin(t, "Bash"))
	var stdout, stderr bytes.Buffer
	run(stdin, &stdout, &stderr, sock, defaultReadTimeout)

	got := decodeOut(t, stdout.Bytes())
	if got.Decision != "block" {
		t.Fatalf("decision = %q, want block", got.Decision)
	}
	if got.Reason != "user denied" {
		t.Fatalf("reason = %q, want 'user denied'", got.Reason)
	}
}

// ----- 3. $RAFRAF_BRIDGE_PERM_SOCK unset → fail safe deny ----------------

func TestHook_NoSockEnvVarDenies(t *testing.T) {
	stdin := bytes.NewReader(mustStdin(t, "Read"))
	var stdout, stderr bytes.Buffer
	run(stdin, &stdout, &stderr, "", defaultReadTimeout)
	got := decodeOut(t, stdout.Bytes())
	if got.Decision != "block" {
		t.Fatalf("decision = %q, want block", got.Decision)
	}
}

// ----- 4. Dial fails (no listener) → deny --------------------------------

func TestHook_DialFailsDenies(t *testing.T) {
	stdin := bytes.NewReader(mustStdin(t, "Read"))
	var stdout, stderr bytes.Buffer
	// Path that doesn't exist anywhere.
	run(stdin, &stdout, &stderr, "/tmp/this-path-does-not-exist-zzz.sock", defaultReadTimeout)
	got := decodeOut(t, stdout.Bytes())
	if got.Decision != "block" {
		t.Fatalf("decision = %q, want block", got.Decision)
	}
}

// ----- 5. Malformed stdin → deny ----------------------------------------

func TestHook_BadStdinDenies(t *testing.T) {
	sock, stop := fakeBroker(t, brokerReply{Decision: "allow"})
	defer stop()
	stdin := bytes.NewReader([]byte("{not json"))
	var stdout, stderr bytes.Buffer
	run(stdin, &stdout, &stderr, sock, defaultReadTimeout)
	got := decodeOut(t, stdout.Bytes())
	if got.Decision != "block" {
		t.Fatalf("decision = %q, want block", got.Decision)
	}
}

// ----- 6. Broker reply EOF → deny ----------------------------------------

func TestHook_BrokerEOFDenies(t *testing.T) {
	sock := shortSock(t)
	ln, err := net.Listen("unix", sock)
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	defer func() { _ = ln.Close() }()
	go func() {
		conn, aerr := ln.Accept()
		if aerr != nil {
			return
		}
		// Close immediately — hook's write may succeed (kernel
		// buffers it) but its subsequent Decode returns EOF, which
		// the hook treats as a reply failure → deny.
		_ = conn.Close()
	}()
	stdin := bytes.NewReader(mustStdin(t, "Edit"))
	var stdout, stderr bytes.Buffer
	run(stdin, &stdout, &stderr, sock, defaultReadTimeout)
	got := decodeOut(t, stdout.Bytes())
	if got.Decision != "block" {
		t.Fatalf("decision = %q, want block", got.Decision)
	}
}

// ----- 7. Broker returns unknown decision → deny -------------------------

func TestHook_UnknownDecisionDenies(t *testing.T) {
	sock, stop := fakeBroker(t, brokerReply{Decision: "weird"})
	defer stop()
	stdin := bytes.NewReader(mustStdin(t, "Read"))
	var stdout, stderr bytes.Buffer
	run(stdin, &stdout, &stderr, sock, defaultReadTimeout)
	got := decodeOut(t, stdout.Bytes())
	if got.Decision != "block" {
		t.Fatalf("decision = %q, want block", got.Decision)
	}
}

// ----- 8. Latency sanity (<200ms over loopback UDS) ----------------------

func TestHook_LatencyBudget(t *testing.T) {
	sock, stop := fakeBroker(t, brokerReply{Decision: "allow"})
	defer stop()
	stdin := bytes.NewReader(mustStdin(t, "Read"))
	var stdout, stderr bytes.Buffer
	start := time.Now()
	run(stdin, &stdout, &stderr, sock, defaultReadTimeout)
	elapsed := time.Since(start)
	if elapsed > 200*time.Millisecond {
		t.Fatalf("hook took %v over loopback; expected <200ms", elapsed)
	}
}

// ----- 9. Default read deadline value ------------------------------------

// TestHook_DefaultReadTimeoutValue locks the static fallback at 190s
// (broker's 180s default + 10s grace). Bumping this without an
// audit invites the same race the V1.4-followup bump fixed — tracked
// here so a stray edit fails CI loudly.
func TestHook_DefaultReadTimeoutValue(t *testing.T) {
	if defaultReadTimeout != 190*time.Second {
		t.Fatalf("defaultReadTimeout = %s, want 190s", defaultReadTimeout)
	}
}

// ----- 10. Env-var-driven read timeout resolver --------------------------

// TestResolveReadTimeout exercises every branch of the
// RAFRAF_BRIDGE_PERM_TIMEOUT_MS resolver. The bridge writes this env
// var alongside the UDS path so the hook's deadline tracks the
// broker's effective permission_timeout config in lockstep — every
// failure mode below would otherwise fall through to the static
// default and break that lockstep.
func TestResolveReadTimeout(t *testing.T) {
	cases := []struct {
		name string
		raw  string
		want time.Duration
	}{
		{"empty", "", defaultReadTimeout},
		{"zero", "0", defaultReadTimeout},
		{"negative", "-1000", defaultReadTimeout},
		{"unparseable", "abc", defaultReadTimeout},
		{"trailing_garbage", "1000foo", defaultReadTimeout},
		{
			"valid_180s",
			"180000",
			180*time.Second + timeoutGrace,
		},
		{
			"valid_60s_dev_override",
			"60000",
			60*time.Second + timeoutGrace,
		},
		{
			"valid_max_600s",
			"600000",
			600*time.Second + timeoutGrace,
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := resolveReadTimeout(tc.raw)
			if got != tc.want {
				t.Fatalf("resolveReadTimeout(%q) = %s, want %s",
					tc.raw, got, tc.want)
			}
		})
	}
}

// ----- 11. Hook honours an explicit short deadline -----------------------

// TestHook_HonoursExplicitShortDeadline verifies that the deadline
// argument propagates all the way to conn.SetDeadline — i.e. when
// the bridge dials the timeout down (low-risk dev environment) the
// hook actually denies faster instead of waiting for the static
// default.
//
// The test stands up a UDS listener that accepts but never replies,
// passes a 100ms deadline, and asserts the hook denies in well
// under the static default.
func TestHook_HonoursExplicitShortDeadline(t *testing.T) {
	sock := shortSock(t)
	ln, err := net.Listen("unix", sock)
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	defer func() { _ = ln.Close() }()
	go func() {
		// Accept and hold — never reply. The hook's read deadline
		// must fire and produce a deny.
		for {
			conn, aerr := ln.Accept()
			if aerr != nil {
				return
			}
			// Hold the connection open so the hook's Decode blocks
			// on the kernel until SetDeadline expires.
			go func(c net.Conn) {
				time.Sleep(2 * time.Second)
				_ = c.Close()
			}(conn)
		}
	}()

	stdin := bytes.NewReader(mustStdin(t, "Read"))
	var stdout, stderr bytes.Buffer
	start := time.Now()
	run(stdin, &stdout, &stderr, sock, 100*time.Millisecond)
	elapsed := time.Since(start)

	got := decodeOut(t, stdout.Bytes())
	if got.Decision != "block" {
		t.Fatalf("decision = %q, want block", got.Decision)
	}
	// Generous upper bound: we want to catch a regression where
	// the hook ignored our deadline arg and fell back to the 190s
	// default. 1s is plenty of slack for scheduler jitter.
	if elapsed > time.Second {
		t.Fatalf("elapsed = %v, want <= 1s (deadline arg ignored?)", elapsed)
	}
}

// ----- 12. Zero/negative deadline arg falls back to default -------------

// TestHook_ZeroDeadlineFallsBackToDefault belt-and-braces test: a
// future caller passing 0 / negative as the deadline arg must NOT
// translate to an immediate timeout (which would deny every request).
// The hook's run() guards against this by snapping back to
// defaultReadTimeout. We only assert the hook didn't deny on a
// happy path — full deadline bound is impractical to assert without
// waiting 190s.
func TestHook_ZeroDeadlineFallsBackToDefault(t *testing.T) {
	sock, stop := fakeBroker(t, brokerReply{Decision: "allow"})
	defer stop()
	stdin := bytes.NewReader(mustStdin(t, "Read"))
	var stdout, stderr bytes.Buffer
	run(stdin, &stdout, &stderr, sock, 0)
	got := decodeOut(t, stdout.Bytes())
	if got.Decision != "allow" {
		t.Fatalf("decision = %q, want allow (zero deadline must NOT fast-deny)",
			got.Decision)
	}
}
