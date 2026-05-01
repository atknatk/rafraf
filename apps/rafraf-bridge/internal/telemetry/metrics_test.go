package telemetry_test

import (
	"encoding/json"
	"expvar"
	"strings"
	"testing"

	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/telemetry"
)

// TestFormatMetricsLine_ContainsAllSections checks that every category from
// docs/11_Bridge_Spec.md §9 is represented in the single-line stderr summary
// the bridge prints every 15s. Tests assert on key tokens rather than the
// full string so it stays trivial to extend.
func TestFormatMetricsLine_ContainsAllSections(t *testing.T) {
	t.Parallel()

	line := telemetry.FormatMetricsLine()

	wantTokens := []string{
		"[metrics]",
		"connected=", "reconnects=", "disconnects=", "events=", "dropped=",
		"claude_active=", "claude_total=", "claude_lines=",
		"rate_limit_hits=", "rate_limit_warn=", "rate_limit_exceeded=",
		"auth_expired=", "cost_usd_x1000=",
		"subagent_spawned=", "subagent_done=", "subagent_failed=",
		"statusline_age=", "statusline_5h=", "statusline_7d=",
		"storage_lag=",
	}
	for _, tok := range wantTokens {
		if !strings.Contains(line, tok) {
			t.Errorf("FormatMetricsLine missing token %q\nfull line: %s", tok, line)
		}
	}
}

// TestAddClaudeCostUSD_AccumulatesAsX1000 confirms the helper applies the
// 1000x scaling and ignores non-positive deltas (the claude CLI reports
// 0.0 for cached turns; bumping the counter would skew it).
func TestAddClaudeCostUSD_AccumulatesAsX1000(t *testing.T) {
	// NOT parallel: mutates a global counter; comparing before/after
	// would race against any sibling test that also touches this counter.

	before := telemetry.ClaudeTotalCostUSDx1000.Load()

	telemetry.AddClaudeCostUSD(0.0)   // ignored
	telemetry.AddClaudeCostUSD(-1.5)  // ignored
	telemetry.AddClaudeCostUSD(0.123) // +123
	telemetry.AddClaudeCostUSD(2.0)   // +2000

	got := telemetry.ClaudeTotalCostUSDx1000.Load() - before
	if got != 2123 {
		t.Errorf("delta = %d, want 2123", got)
	}
}

// TestSetBridgeVersion_PublishesViaExpvar verifies bridgeVersion shows up in
// the expvar registry under "bridge_version" — the only way we publish it.
// This indirectly also exercises the init() hook that wires every gauge
// into the registry.
func TestSetBridgeVersion_PublishesViaExpvar(t *testing.T) {
	// NOT parallel: writes shared expvar state.

	telemetry.SetBridgeVersion("v9.9.9-test")

	v := expvar.Get("bridge_version")
	if v == nil {
		t.Fatal(`expvar.Get("bridge_version") returned nil — init() did not publish`)
	}
	// expvar serialises Func values as JSON. For a plain string we expect
	// the JSON-encoded form to be the quoted string itself.
	got := strings.TrimSpace(v.String())
	want := `"v9.9.9-test"`
	if got != want {
		t.Errorf("expvar bridge_version = %q, want %q", got, want)
	}
}

// TestExpvarCatalog_AllNamesPresent walks the expvar registry and asserts
// each canonical Doc 11 §9 metric name has been published. This is the
// regression test that catches an init() hook accidentally dropping an
// entry during a future refactor.
func TestExpvarCatalog_AllNamesPresent(t *testing.T) {
	t.Parallel()

	wantNames := []string{
		// bridge meta
		"bridge_uptime_seconds",
		"bridge_version",
		// ws
		"ws_connected",
		"ws_reconnects_total",
		"ws_disconnects_total",
		"ws_events_forwarded_total",
		"ws_events_dropped_total",
		// claude
		"claude_subprocess_active",
		"claude_subprocess_total",
		"claude_stream_lines_read_total",
		"claude_rate_limit_hits_total",
		"claude_rate_limit_warnings_total",
		"claude_rate_limit_exceeded_total",
		"claude_auth_expired_total",
		"claude_total_cost_usd_x1000",
		// subagent
		"subagent_spawned_total",
		"subagent_completed_total",
		"subagent_failed_total",
		// storage
		"storage_watcher_events_total",
		"storage_watcher_lag_seconds",
		// statusline
		"statusline_last_report_age_seconds",
		"statusline_five_hour_pct",
		"statusline_seven_day_pct",
	}
	for _, name := range wantNames {
		if expvar.Get(name) == nil {
			t.Errorf("expvar var %q not published — Doc 11 §9 catalogue is incomplete", name)
		}
	}
}

// TestExpvarValuesAreJSONNumbers ensures the Func wrappers emit raw JSON
// numbers rather than strings — important because dashboards parse them
// with `jq '.<name> | tonumber'` style chains.
func TestExpvarValuesAreJSONNumbers(t *testing.T) {
	// NOT parallel: mutates a shared atomic counter.

	telemetry.WSReconnects.Add(42)
	v := expvar.Get("ws_reconnects_total")
	if v == nil {
		t.Fatal("ws_reconnects_total not published")
	}
	// expvar.Func.String returns the JSON encoding of the wrapped value.
	// json.Number.UnmarshalJSON accepts only valid JSON numbers.
	var n json.Number
	if err := json.Unmarshal([]byte(v.String()), &n); err != nil {
		t.Fatalf("ws_reconnects_total emitted non-numeric JSON %q: %v", v.String(), err)
	}
}
