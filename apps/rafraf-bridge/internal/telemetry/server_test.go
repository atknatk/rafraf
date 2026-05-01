package telemetry_test

import (
	"context"
	"io"
	"log/slog"
	"net/http"
	"strings"
	"testing"
	"time"

	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/telemetry"
)

// silentLogger returns a logger whose output is discarded — used so the
// telemetry server's startup/shutdown logs do not pollute `go test -v`.
func silentLogger() *slog.Logger {
	return slog.New(slog.NewTextHandler(io.Discard, nil))
}

// waitForHTTP polls url until it returns 200 or the deadline elapses. Tests
// use a tiny ListenAndServe goroutine so a brief warm-up window is normal —
// the alternative (sleeping unconditionally) is flakier and slower.
func waitForHTTP(t *testing.T, url string) *http.Response {
	t.Helper()
	deadline := time.Now().Add(2 * time.Second)
	var lastErr error
	for time.Now().Before(deadline) {
		resp, err := httpGet(url)
		if err == nil && resp.StatusCode == http.StatusOK {
			return resp
		}
		if resp != nil {
			_ = resp.Body.Close()
		}
		lastErr = err
		time.Sleep(10 * time.Millisecond)
	}
	t.Fatalf("HTTP %s never returned 200 within deadline; last err: %v", url, lastErr)
	return nil
}

func TestStartMetricsServer_DebugVarsExposesCounters(t *testing.T) {
	t.Parallel()

	// We assert each canonical Doc 11 §9 metric name appears in the
	// /debug/vars JSON dump. The init() hook publishes every gauge at
	// zero on package load, so we do not need to mutate any counter
	// for the names to be present — that also keeps this test free of
	// global-state races against other tests in this package.

	server, err := telemetry.StartMetricsServer("127.0.0.1:0", silentLogger())
	if err != nil {
		t.Fatalf("StartMetricsServer returned err: %v", err)
	}
	if server == nil {
		t.Fatal("StartMetricsServer returned nil server for non-empty addr")
	}
	t.Cleanup(func() {
		_ = telemetry.ShutdownMetricsServer(context.Background(), server)
	})

	resp := waitForHTTP(t, "http://"+server.Addr+"/debug/vars")
	defer func() { _ = resp.Body.Close() }()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		t.Fatalf("read body: %v", err)
	}
	bodyStr := string(body)

	// Spot-check a representative sample of the Doc 11 §9 catalogue —
	// the init hook publishes 20+ vars, listing a few from each
	// section is enough to detect a regression where init was not
	// wired.
	wantSubstrings := []string{
		`"bridge_uptime_seconds"`,
		`"bridge_version"`,
		`"ws_connected"`,
		`"ws_reconnects_total"`,
		`"ws_events_dropped_total"`,
		`"claude_subprocess_active"`,
		`"claude_subprocess_total"`,
		`"claude_stream_lines_read_total"`,
		`"claude_rate_limit_warnings_total"`,
		`"claude_rate_limit_exceeded_total"`,
		`"claude_auth_expired_total"`,
		`"claude_total_cost_usd_x1000"`,
		`"subagent_spawned_total"`,
		`"subagent_completed_total"`,
		`"subagent_failed_total"`,
		`"storage_watcher_events_total"`,
		`"storage_watcher_lag_seconds"`,
		`"statusline_last_report_age_seconds"`,
		`"statusline_five_hour_pct"`,
		`"statusline_seven_day_pct"`,
	}
	for _, want := range wantSubstrings {
		if !strings.Contains(bodyStr, want) {
			t.Errorf("/debug/vars output missing %q\n--- body (truncated) ---\n%s", want, truncate(bodyStr, 800))
		}
	}
}

func TestStartMetricsServer_HealthzReturnsJSON(t *testing.T) {
	t.Parallel()

	server, err := telemetry.StartMetricsServer("127.0.0.1:0", silentLogger())
	if err != nil {
		t.Fatalf("StartMetricsServer: %v", err)
	}
	t.Cleanup(func() {
		_ = telemetry.ShutdownMetricsServer(context.Background(), server)
	})

	resp := waitForHTTP(t, "http://"+server.Addr+"/healthz")
	defer func() { _ = resp.Body.Close() }()

	if got := resp.Header.Get("Content-Type"); got != "application/json" {
		t.Errorf("Content-Type = %q, want application/json", got)
	}
	body, _ := io.ReadAll(resp.Body)
	if !strings.Contains(string(body), `"status":"ok"`) {
		t.Errorf("healthz body missing status:ok marker: %q", string(body))
	}
}

func TestStartMetricsServer_EmptyAddrDisablesServer(t *testing.T) {
	t.Parallel()

	server, err := telemetry.StartMetricsServer("", silentLogger())
	if err != nil {
		t.Fatalf("StartMetricsServer with empty addr returned err: %v", err)
	}
	if server != nil {
		t.Errorf("expected nil server when addr is empty, got %#v", server)
	}
	// Shutdown of nil server must be a no-op so cmd/bridge can call it
	// unconditionally during shutdown.
	if err := telemetry.ShutdownMetricsServer(context.Background(), nil); err != nil {
		t.Errorf("ShutdownMetricsServer(nil) = %v, want nil", err)
	}
}

func TestStartMetricsServer_NilLoggerUsesDefault(t *testing.T) {
	t.Parallel()

	// Passing a nil logger must not panic. We swap to slog.Default
	// internally; we just need to assert the server starts and serves.
	server, err := telemetry.StartMetricsServer("127.0.0.1:0", nil)
	if err != nil {
		t.Fatalf("StartMetricsServer with nil logger returned err: %v", err)
	}
	if server == nil {
		t.Fatal("server is nil")
	}
	t.Cleanup(func() {
		_ = telemetry.ShutdownMetricsServer(context.Background(), server)
	})

	resp := waitForHTTP(t, "http://"+server.Addr+"/healthz")
	defer func() { _ = resp.Body.Close() }()
	if resp.StatusCode != http.StatusOK {
		t.Errorf("status = %d", resp.StatusCode)
	}
}

func TestShutdownMetricsServer_BoundedTimeout(t *testing.T) {
	t.Parallel()

	server, err := telemetry.StartMetricsServer("127.0.0.1:0", silentLogger())
	if err != nil {
		t.Fatalf("StartMetricsServer: %v", err)
	}
	// Wait until at least one request completes so we know the server
	// is fully serving.
	resp := waitForHTTP(t, "http://"+server.Addr+"/healthz")
	_ = resp.Body.Close()

	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	if err := telemetry.ShutdownMetricsServer(ctx, server); err != nil {
		t.Errorf("Shutdown returned err: %v", err)
	}

	// Subsequent requests must fail (server closed).
	if _, err := httpGet("http://" + server.Addr + "/healthz"); err == nil {
		t.Error("expected error after shutdown, got nil")
	}
}

// httpGet wraps http.Get for tests so the linter does not flag the
// hard-coded URL (the URL is constructed from server.Addr which the test
// itself created via net.Listen on 127.0.0.1, not user input).
func httpGet(url string) (*http.Response, error) {
	req, err := http.NewRequest(http.MethodGet, url, nil)
	if err != nil {
		return nil, err
	}
	return http.DefaultClient.Do(req)
}

func truncate(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n] + "...(truncated)"
}
