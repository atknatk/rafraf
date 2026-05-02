package telemetry_test

import (
	"context"
	"io"
	"net/http"
	"strings"
	"testing"

	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/telemetry"
)

// TestStartMetricsServer_PromMetricsExposesAllCounters asserts the
// /metrics endpoint serves a Prometheus exposition body containing every
// counter/gauge mirrored from the existing expvar surface (Doc 11 §9 →
// T2.2). The test mutates a couple of atomics so we also verify a
// non-zero value flows through Collect; the rest are checked by name.
func TestStartMetricsServer_PromMetricsExposesAllCounters(t *testing.T) {
	t.Parallel()

	telemetry.SetPromIdentity("test-version", "test-host")
	telemetry.WSReconnects.Store(7)
	telemetry.ClaudeTotalCostUSDx1000.Store(1234) // = $1.234
	// Force at least one rename-collision metric to a known value so we
	// can pin the namespaced output line below (regression for T2.2-fix
	// M3 — naming change MUST surface in /metrics).
	telemetry.SubagentSpawnedTotal.Store(3)

	server, err := telemetry.StartMetricsServer("127.0.0.1:0", silentLogger())
	if err != nil {
		t.Fatalf("StartMetricsServer: %v", err)
	}
	t.Cleanup(func() {
		_ = telemetry.ShutdownMetricsServer(context.Background(), server)
	})

	resp := waitForHTTP(t, "http://"+server.Addr+"/metrics")
	defer func() { _ = resp.Body.Close() }()

	contentType := resp.Header.Get("Content-Type")
	// promhttp.Handler emits Prometheus exposition; the version string
	// changes between client_golang releases (e.g. "0.0.4" vs newer
	// OpenMetrics negotiations) so we only assert the prefix.
	if !strings.HasPrefix(contentType, "text/plain") &&
		!strings.HasPrefix(contentType, "application/openmetrics-text") {
		t.Errorf("Content-Type = %q, want text/plain* or openmetrics", contentType)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		t.Fatalf("read body: %v", err)
	}
	bodyStr := string(body)

	// Names that MUST appear (Prometheus expansion of expvar Doc 11 §9).
	// T2.2-fix M3: four metrics use the bridge_ prefix to avoid colliding
	// with the backend's same-named families on a shared scrape.
	wantNames := []string{
		"bridge_uptime_seconds",
		"ws_connected",
		"ws_reconnects_total",
		"ws_disconnects_total",
		"ws_events_forwarded_total",
		"ws_events_dropped_total",
		"claude_subprocess_active",
		"claude_subprocess_total",
		"claude_stream_lines_read_total",
		"bridge_claude_rate_limit_hits_total",
		"claude_rate_limit_warnings_total",
		"claude_rate_limit_exceeded_total",
		"claude_auth_expired_total",
		"bridge_claude_total_cost_usd_total",
		"bridge_subagent_spawned_total",
		"subagent_completed_total",
		"subagent_failed_total",
		"bridge_storage_watcher_lag_seconds",
		"statusline_last_report_age_seconds",
		"statusline_five_hour_pct",
		"statusline_seven_day_pct",
	}

	// T2.2-fix M3 regression: the un-prefixed (backend canonical) names
	// MUST NOT appear in the bridge body; if they do, the rename was
	// reverted and a Prometheus scrape collision with the backend will
	// silently mask data on the storage layer.
	mustNotAppear := []string{
		"\nclaude_rate_limit_hits_total{",
		"\nclaude_total_cost_usd_total{",
		"\nsubagent_spawned_total{",
		"\nstorage_watcher_lag_seconds{",
	}
	for _, banned := range mustNotAppear {
		if strings.Contains(bodyStr, banned) {
			t.Errorf("bridge /metrics MUST NOT publish %q (collides with backend canonical name)", strings.TrimPrefix(banned, "\n"))
		}
	}
	for _, name := range wantNames {
		if !strings.Contains(bodyStr, name) {
			t.Errorf("/metrics output missing %q\n--- body (truncated) ---\n%s",
				name, truncate(bodyStr, 1200))
		}
	}

	// Identity labels must show up on at least one sample line.
	if !strings.Contains(bodyStr, `bridge_version="test-version"`) {
		t.Error("missing bridge_version label")
	}
	if !strings.Contains(bodyStr, `host_id="test-host"`) {
		t.Error("missing host_id label")
	}

	// Non-zero atomic must surface in the body. Counter samples include
	// the labelset between the name and value, e.g.:
	//   ws_reconnects_total{bridge_version="test-version",host_id="test-host"} 7
	if !strings.Contains(bodyStr, "ws_reconnects_total{") ||
		!strings.Contains(bodyStr, " 7") {
		t.Error("expected ws_reconnects_total counter to surface value 7")
	}
	// Cost counter must convert the *1000 storage trick back to USD —
	// 1234 → 1.234. We check for the exact substring.
	if !strings.Contains(bodyStr, "1.234") {
		t.Error(
			"expected bridge_claude_total_cost_usd_total to expose " +
				"value 1.234",
		)
	}
	// And the value must be tagged with the namespaced metric name (the
	// regression for T2.2-fix M3 — guarantees the cost sample isn't being
	// emitted under the un-prefixed backend-canonical name).
	if !strings.Contains(bodyStr, "bridge_claude_total_cost_usd_total{") {
		t.Error("expected bridge_claude_total_cost_usd_total sample line to be present")
	}
	// Subagent counter regression: same shape — 3 subagents stored above.
	if !strings.Contains(bodyStr, "bridge_subagent_spawned_total{") {
		t.Error("expected bridge_subagent_spawned_total sample line to be present")
	}
}

// TestStartMetricsServer_DebugVarsRemainsAvailable ensures /metrics is
// mounted ALONGSIDE /debug/vars rather than replacing it (back-compat
// requirement — Faz 0.5 stderr summary + dashboards still scrape expvar).
func TestStartMetricsServer_DebugVarsRemainsAvailable(t *testing.T) {
	t.Parallel()

	server, err := telemetry.StartMetricsServer("127.0.0.1:0", silentLogger())
	if err != nil {
		t.Fatalf("StartMetricsServer: %v", err)
	}
	t.Cleanup(func() {
		_ = telemetry.ShutdownMetricsServer(context.Background(), server)
	})

	// Both endpoints should serve 200.
	resp := waitForHTTP(t, "http://"+server.Addr+"/debug/vars")
	_ = resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Errorf("/debug/vars status = %d, want 200", resp.StatusCode)
	}
	resp = waitForHTTP(t, "http://"+server.Addr+"/metrics")
	_ = resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Errorf("/metrics status = %d, want 200", resp.StatusCode)
	}
}

// TestPromRegistry_IdentitySetterUpdatesLabels verifies SetPromIdentity
// influences subsequent Collect calls (no need to restart the server).
func TestPromRegistry_IdentitySetterUpdatesLabels(t *testing.T) {
	// NOTE: Not parallel — mutates package-private label state shared
	// with the parallel test above. The other tests use distinct
	// identity values, so the final assertion here is the source of
	// truth for the labels at the point we read /metrics.
	telemetry.SetPromIdentity("v9.9.9", "host-X")

	server, err := telemetry.StartMetricsServer("127.0.0.1:0", silentLogger())
	if err != nil {
		t.Fatalf("StartMetricsServer: %v", err)
	}
	t.Cleanup(func() {
		_ = telemetry.ShutdownMetricsServer(context.Background(), server)
	})

	resp := waitForHTTP(t, "http://"+server.Addr+"/metrics")
	defer func() { _ = resp.Body.Close() }()
	body, _ := io.ReadAll(resp.Body)
	if !strings.Contains(string(body), `bridge_version="v9.9.9"`) {
		t.Error("expected bridge_version label to update via SetPromIdentity")
	}
	if !strings.Contains(string(body), `host_id="host-X"`) {
		t.Error("expected host_id label to update via SetPromIdentity")
	}
}
