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
	run(stdin, &stdout, &stderr, sock)

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
	run(stdin, &stdout, &stderr, sock)

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
	run(stdin, &stdout, &stderr, "")
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
	run(stdin, &stdout, &stderr, "/tmp/this-path-does-not-exist-zzz.sock")
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
	run(stdin, &stdout, &stderr, sock)
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
	run(stdin, &stdout, &stderr, sock)
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
	run(stdin, &stdout, &stderr, sock)
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
	run(stdin, &stdout, &stderr, sock)
	elapsed := time.Since(start)
	if elapsed > 200*time.Millisecond {
		t.Fatalf("hook took %v over loopback; expected <200ms", elapsed)
	}
}
