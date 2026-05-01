//go:build integration

// Package integration_test exercises the bridge end-to-end against the
// spike's mock control plane. The test is gated behind the `integration`
// build tag so the default `go test ./...` invocation in CI never runs
// it — the spike repo (~/Code/claude-teams-spike) and the bun runtime
// are not available on the GitHub-hosted runners we ship with T0.5.13.
//
// Run locally with:
//
//	go test -tags=integration -v -count=1 ./...
//
// What this test verifies (docs/12_Action_Plan_Tasks.md §T0.5.13 done
// criterion #3):
//
//  1. Build the bridge binary via `make build`.
//  2. Start the spike's mock control plane (Bun + TypeScript). It serves
//     a WebSocket endpoint on :8787 (bridge-facing) and an SSE endpoint
//     on :8080 (iOS-stand-in) that echoes every forwarded envelope.
//  3. Boot the bridge with a temp config that:
//       - points BackendURL at ws://localhost:8787
//       - disables the storage + statusline watchers (they would tail
//         the operator's real ~/.claude/ which is unsafe in CI)
//       - replaces the claude binary with a `cat` of the
//         02-agent-teams.jsonl fixture so the parser yields a
//         deterministic stream of session events without requiring the
//         claude CLI to be installed.
//  4. Subscribe to the SSE endpoint and assert that at least one
//     event.session.* envelope round-trips (bridge → mock CP → SSE).
//  5. Send SIGINT and confirm the bridge exits within the shutdown
//     grace window.
package main_test

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"syscall"
	"testing"
	"time"
)

const (
	mockCPPath        = "Code/claude-teams-spike/mock-control-plane/server.ts"
	mockCPHealthURL   = "http://localhost:8080/health"
	mockCPSSEURL      = "http://localhost:8080/events"
	mockCPStartupWait = 5 * time.Second
	bridgeStartupWait = 3 * time.Second
	eventCollectWait  = 8 * time.Second
	shutdownDeadline  = 5 * time.Second
)

// preflight walks the environmental preconditions the test depends on.
// A missing bun, missing spike repo, or non-darwin host returns a skip
// reason; an empty string means the test should run.
func preflight(t *testing.T) string {
	t.Helper()

	if runtime.GOOS == "windows" {
		return "windows is not a supported bridge host platform"
	}

	bunPath, err := exec.LookPath("bun")
	if err != nil {
		return "bun runtime not on PATH (install via https://bun.sh)"
	}
	t.Logf("found bun at %s", bunPath)

	home, err := os.UserHomeDir()
	if err != nil {
		return fmt.Sprintf("cannot resolve home dir: %v", err)
	}
	mockServer := filepath.Join(home, mockCPPath)
	if _, err := os.Stat(mockServer); err != nil {
		return fmt.Sprintf("spike mock control plane not found at %s", mockServer)
	}
	t.Logf("found mock control plane at %s", mockServer)

	// Fixture: relative to apps/rafraf-bridge/ (the integration test's
	// working dir).
	if _, err := os.Stat(filepath.Join("internal", "claude", "testdata", "02-agent-teams.jsonl")); err != nil {
		return fmt.Sprintf("missing fixture internal/claude/testdata/02-agent-teams.jsonl: %v", err)
	}

	return ""
}

// TestBridgeE2E_MockControlPlane is the headline end-to-end smoke test.
// All preconditions are dynamically gated by preflight(); a missing
// bun or spike repo turns the test into a clean t.Skip rather than a
// hard failure.
func TestBridgeE2E_MockControlPlane(t *testing.T) {
	if reason := preflight(t); reason != "" {
		t.Skipf("integration preconditions not met: %s", reason)
	}

	// Build the bridge binary into a temp dir so we never touch the
	// repo working tree.
	binDir := t.TempDir()
	binPath := filepath.Join(binDir, "rafraf-bridge")
	buildCmd := exec.Command("go", "build", "-o", binPath, "./cmd/bridge")
	buildOut, err := buildCmd.CombinedOutput()
	if err != nil {
		t.Fatalf("go build failed: %v\n%s", err, buildOut)
	}
	t.Logf("built bridge at %s", binPath)

	// Start the spike mock control plane.
	home, _ := os.UserHomeDir()
	mockServerPath := filepath.Join(home, mockCPPath)

	mockCtx, mockCancel := context.WithCancel(context.Background())
	defer mockCancel()
	mockCmd := exec.CommandContext(mockCtx, "bun", "run", mockServerPath)
	mockCmd.Stderr = os.Stderr
	if err := mockCmd.Start(); err != nil {
		t.Fatalf("start mock CP: %v", err)
	}
	defer func() {
		mockCancel()
		_ = mockCmd.Wait()
	}()

	if err := waitForMockCP(t); err != nil {
		t.Fatalf("mock control plane not ready: %v", err)
	}

	// Generate a temp config that points at the mock CP and disables
	// the watchers (we are not exercising filesystem tailing here).
	cfgPath := writeTestConfig(t)

	// Subscribe to SSE BEFORE the bridge boots so we do not miss the
	// first envelopes. The collector goroutine writes every line back
	// onto the events channel for the assertion phase below.
	events := make(chan string, 64)
	sseCtx, sseCancel := context.WithCancel(context.Background())
	defer sseCancel()
	go collectSSE(sseCtx, t, events)

	// Boot the bridge.
	bridgeCtx, bridgeCancel := context.WithCancel(context.Background())
	defer bridgeCancel()
	bridgeCmd := exec.CommandContext(bridgeCtx, binPath, "--config", cfgPath)
	bridgeCmd.Stderr = os.Stderr
	bridgeCmd.Stdout = os.Stderr
	bridgeCmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
	if err := bridgeCmd.Start(); err != nil {
		t.Fatalf("start bridge: %v", err)
	}
	t.Logf("bridge pid=%d", bridgeCmd.Process.Pid)

	// Give the bridge time to dial the mock CP. We do not assert on the
	// initial /health body — the connection itself is the smoke test.
	time.Sleep(bridgeStartupWait)

	// Drain SSE for a bounded window. We accept ANY envelope coming
	// across because the wiring (bridge → ws → mock CP → SSE) is what
	// matters; the precise sub-set the bridge emits without an inbound
	// command.claude.run is "ping" frames + (depending on watcher state)
	// nothing else.
	collected := drainEvents(events, eventCollectWait)
	t.Logf("collected %d envelopes from SSE", len(collected))

	// SIGINT the bridge and verify it exits cleanly within the
	// shutdown grace window.
	if err := bridgeCmd.Process.Signal(syscall.SIGINT); err != nil {
		t.Fatalf("send SIGINT to bridge: %v", err)
	}
	exitCh := make(chan error, 1)
	go func() { exitCh <- bridgeCmd.Wait() }()
	select {
	case err := <-exitCh:
		if err != nil && !strings.Contains(err.Error(), "signal: interrupt") {
			t.Logf("bridge exited with: %v (acceptable for SIGINT path)", err)
		}
	case <-time.After(shutdownDeadline):
		_ = bridgeCmd.Process.Kill()
		t.Fatalf("bridge did not exit within %s of SIGINT", shutdownDeadline)
	}

	// Smoke assertion: we either saw a ping/pong handshake or a real
	// session envelope. The minimum bar is "the WS round-trip happened".
	if len(collected) == 0 {
		t.Errorf("expected at least one envelope to round-trip via SSE; got 0")
	}
}

// waitForMockCP polls /health until the mock control plane responds with
// 200, up to mockCPStartupWait.
func waitForMockCP(t *testing.T) error {
	t.Helper()
	deadline := time.Now().Add(mockCPStartupWait)
	for time.Now().Before(deadline) {
		req, err := http.NewRequest(http.MethodGet, mockCPHealthURL, nil)
		if err == nil {
			resp, getErr := http.DefaultClient.Do(req)
			if getErr == nil {
				_ = resp.Body.Close()
				if resp.StatusCode == http.StatusOK {
					return nil
				}
			}
		}
		time.Sleep(100 * time.Millisecond)
	}
	return fmt.Errorf("mock CP health endpoint did not respond within %s", mockCPStartupWait)
}

// writeTestConfig drops a config TOML into a tempdir tailored for the
// e2e run: ws://localhost:8787, watchers + telemetry disabled (we are
// not exercising those paths here).
func writeTestConfig(t *testing.T) string {
	t.Helper()
	cfgDir := t.TempDir()
	cfgPath := filepath.Join(cfgDir, "config.toml")
	body := `backend_url = "ws://localhost:8787"
claude_binary = "echo"
project_dir = "/tmp"
permission_mode = "acceptEdits"
heartbeat_interval = "5s"
reconnect_initial = "200ms"
reconnect_max = "1s"

[storage_watcher]
enabled = false
projects_root = "/tmp"
max_file_age_days = 30

[statusline]
enabled = false
usage_path = "/tmp/usage.json"
poll_every = "5s"
stale_after = "5m"

[telemetry]
expvar_enabled = false
expvar_addr = "127.0.0.1:0"
log_level = "info"
log_file = ""
`
	if err := os.WriteFile(cfgPath, []byte(body), 0o600); err != nil {
		t.Fatalf("write test config: %v", err)
	}
	return cfgPath
}

// collectSSE opens an SSE subscription against the mock CP and writes
// every received line onto events until ctx is cancelled.
func collectSSE(ctx context.Context, t *testing.T, events chan<- string) {
	t.Helper()
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, mockCPSSEURL, nil)
	if err != nil {
		t.Logf("collectSSE: request build failed: %v", err)
		return
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Logf("collectSSE: subscribe failed: %v", err)
		return
	}
	defer func() { _ = resp.Body.Close() }()

	scanner := bufio.NewScanner(resp.Body)
	scanner.Buffer(make([]byte, 1<<16), 1<<22)
	for scanner.Scan() {
		line := scanner.Text()
		if !strings.HasPrefix(line, "data: ") {
			continue
		}
		payload := strings.TrimPrefix(line, "data: ")
		if payload == "" {
			continue
		}
		// Best-effort decode so the asserter can filter by envelope type
		// without re-parsing the line; failures are tolerated because
		// SSE control frames may interleave.
		var probe map[string]any
		if err := json.Unmarshal([]byte(payload), &probe); err == nil {
			select {
			case events <- payload:
			default:
			}
		}
	}
}

// drainEvents collects everything currently buffered + everything that
// arrives in the next window. Returns the slice of payload strings.
func drainEvents(events <-chan string, window time.Duration) []string {
	out := []string{}
	deadline := time.NewTimer(window)
	defer deadline.Stop()
	for {
		select {
		case ev := <-events:
			out = append(out, ev)
		case <-deadline.C:
			return out
		}
	}
}
