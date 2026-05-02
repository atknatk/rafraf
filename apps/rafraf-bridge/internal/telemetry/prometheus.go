// Prometheus exposition for the bridge (T2.2 + T2.2-fix).
//
// The bridge already publishes a Doc 11 §9-canonical expvar surface on
// /debug/vars (see metrics.go). Prometheus is layered alongside it —
// /metrics is mounted on the same telemetry HTTP server (server.go) and
// every counter/gauge mirrors an existing expvar. expvar is preserved
// for the legacy stderr “[metrics]“ line + any ad-hoc tooling that
// already scrapes /debug/vars.
//
// Cardinality control: every metric carries the static
// (bridge_version, host_id) labelset so a multi-bridge scrape
// (one Prometheus, N bridges) can attribute spikes correctly without
// requiring relabel rules in the scrape config.
//
// Cross-target name disambiguation (T2.2-fix M3): four metric NAMES
// previously collided with backend (Python) Prometheus families that
// publish the same logical signal at finer granularity. Because both
// targets are scraped by the same Prometheus instance and a name
// collision with different (label-set, type) tuples is a hard error in
// the storage layer, every collision-prone bridge metric is now
// prefixed with “bridge_” to namespace it explicitly. Renamed:
//
//	claude_total_cost_usd_total      -> bridge_claude_total_cost_usd_total
//	claude_rate_limit_hits_total     -> bridge_claude_rate_limit_hits_total
//	subagent_spawned_total           -> bridge_subagent_spawned_total
//	storage_watcher_lag_seconds      -> bridge_storage_watcher_lag_seconds
//
// The backend continues to publish the canonical (per-session,
// per-rate-limit-type) family under the un-prefixed name; the bridge's
// counterpart is a coarse aggregate keyed by (bridge_version, host_id)
// useful for fleet-level dashboards.
//
// Why a separate registry? Using “prometheus.NewRegistry()“ (rather
// than “prometheus.DefaultRegisterer“) keeps third-party packages
// — most notably anything that auto-registers “go_*“ collectors on
// the default registry — from leaking process-internal metrics we
// don't want to publish from the bridge. Tests can also stand up a
// fresh registry per case.
package telemetry

import (
	"net/http"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
)

// promRegistry is the single backend for /metrics. Built lazily by
// initPromMetrics so package-level construction stays cheap and so
// SetPromIdentity (called by cmd/bridge once host_id is known) can
// influence the labelset before any Collect happens.
var (
	promRegistry *prometheus.Registry

	promBridgeVersion = "unknown"
	promHostID        = "unknown"

	// promCollector wraps the existing atomic counters/gauges into the
	// prometheus.Collector interface so we don't have to dual-write the
	// hot path. See bridgeCollector below.
	promCollector *bridgeCollector
)

// SetPromIdentity records the static (bridge_version, host_id) labels
// used by every Prometheus metric the bridge exposes. Safe to call once
// at startup from cmd/bridge after the config + version are known —
// subsequent calls overwrite the labels (no-op for a single-bridge
// process; useful for hot-config-reload tests).
//
// Calling SetPromIdentity AFTER initPromMetrics still takes effect
// because the labels are read on every Collect call (not snapshotted at
// registration time).
func SetPromIdentity(bridgeVersion, hostID string) {
	if bridgeVersion != "" {
		promBridgeVersion = bridgeVersion
	}
	if hostID != "" {
		promHostID = hostID
	}
}

// PromRegistry returns the bridge's Prometheus registry, lazily building
// it on first call. Exported so tests + the HTTP mux can both reach the
// same instance without a global double-init race.
func PromRegistry() *prometheus.Registry {
	if promRegistry == nil {
		initPromMetrics()
	}
	return promRegistry
}

// PromHandler returns an HTTP handler that serves the bridge's
// /metrics endpoint backed by the package-private Prometheus registry.
// Used by server.go to wire the route alongside /debug/vars.
func PromHandler() http.Handler {
	return promhttp.HandlerFor(PromRegistry(), promhttp.HandlerOpts{
		// Continue to serve a partial body if any single Collect fails
		// — the bridge has no upstream that can recover from a 500 here
		// and an empty page is better than no page during a degraded
		// state.
		ErrorHandling: promhttp.ContinueOnError,
	})
}

func initPromMetrics() {
	promRegistry = prometheus.NewRegistry()
	promCollector = newBridgeCollector()
	promRegistry.MustRegister(promCollector)
}

// ---------------------------------------------------------------------------
// Custom collector: mirrors the atomic counters in metrics.go without
// duplicating storage. Every Collect call snapshots the atomics and emits
// one sample per metric, labelled with (bridge_version, host_id).
// ---------------------------------------------------------------------------

type bridgeCollector struct {
	// Bridge meta
	uptimeSecondsDesc *prometheus.Desc

	// WebSocket
	wsConnectedDesc       *prometheus.Desc
	wsReconnectsDesc      *prometheus.Desc
	wsDisconnectsDesc     *prometheus.Desc
	wsEventsForwardedDesc *prometheus.Desc
	wsEventsDroppedDesc   *prometheus.Desc

	// Claude subprocess
	claudeSubprocessActiveDesc  *prometheus.Desc
	claudeSubprocessTotalDesc   *prometheus.Desc
	claudeLinesReadDesc         *prometheus.Desc
	claudeRateLimitHitsDesc     *prometheus.Desc
	claudeRateLimitWarningsDesc *prometheus.Desc
	claudeRateLimitExceededDesc *prometheus.Desc
	claudeAuthExpiredDesc       *prometheus.Desc
	claudeTotalCostUSDDesc      *prometheus.Desc

	// Subagent
	subagentSpawnedDesc   *prometheus.Desc
	subagentCompletedDesc *prometheus.Desc
	subagentFailedDesc    *prometheus.Desc

	// Storage watcher
	storageWatcherLagSecondsDesc *prometheus.Desc

	// Statusline
	statuslineLastReportAgeDesc *prometheus.Desc
	statuslineFiveHourPctDesc   *prometheus.Desc
	statuslineSevenDayPctDesc   *prometheus.Desc
}

func newBridgeCollector() *bridgeCollector {
	labels := []string{"bridge_version", "host_id"}
	d := func(name, help string) *prometheus.Desc {
		return prometheus.NewDesc(name, help, labels, nil)
	}
	return &bridgeCollector{
		uptimeSecondsDesc: d(
			"bridge_uptime_seconds",
			"Wall-clock seconds since the bridge process started.",
		),

		wsConnectedDesc: d(
			"ws_connected",
			"1 while the bridge↔backend WebSocket is up, 0 otherwise.",
		),
		wsReconnectsDesc: d(
			"ws_reconnects_total",
			"Successful (re)connects to the backend WebSocket.",
		),
		wsDisconnectsDesc: d(
			"ws_disconnects_total",
			"Observed WebSocket disconnects.",
		),
		wsEventsForwardedDesc: d(
			"ws_events_forwarded_total",
			"Envelopes successfully written to the backend WebSocket.",
		),
		wsEventsDroppedDesc: d(
			"ws_events_dropped_total",
			"Envelopes dropped because the outbox was full.",
		),

		claudeSubprocessActiveDesc: d(
			"claude_subprocess_active",
			"Currently running claude subprocesses.",
		),
		claudeSubprocessTotalDesc: d(
			"claude_subprocess_total",
			"Cumulative number of claude subprocesses launched.",
		),
		claudeLinesReadDesc: d(
			"claude_stream_lines_read_total",
			"Stream-JSON lines read from claude stdout.",
		),
		claudeRateLimitHitsDesc: d(
			"bridge_claude_rate_limit_hits_total",
			"Aggregate rate_limit_event lines (warning + exceeded). "+
				"Bridge-side coarse aggregate; backend publishes the "+
				"per-rate_limit_type family under "+
				"claude_rate_limit_hits_total.",
		),
		claudeRateLimitWarningsDesc: d(
			"claude_rate_limit_warnings_total",
			"rate_limit_event lines whose status was 'warning'.",
		),
		claudeRateLimitExceededDesc: d(
			"claude_rate_limit_exceeded_total",
			"rate_limit_event lines whose status indicated quota exhaustion.",
		),
		claudeAuthExpiredDesc: d(
			"claude_auth_expired_total",
			"Times the bridge observed an expired/invalid claude auth state.",
		),
		claudeTotalCostUSDDesc: d(
			"bridge_claude_total_cost_usd_total",
			"Cumulative claude session cost in USD. Bridge-side coarse "+
				"aggregate; backend publishes the per-session family "+
				"under claude_total_cost_usd_total.",
		),

		subagentSpawnedDesc: d(
			"bridge_subagent_spawned_total",
			"Subagents (Task tool) the parser observed being spawned. "+
				"Bridge-side coarse aggregate; backend publishes the "+
				"per-status family under subagent_spawned_total.",
		),
		subagentCompletedDesc: d(
			"subagent_completed_total",
			"Subagents that emitted a terminal success result.",
		),
		subagentFailedDesc: d(
			"subagent_failed_total",
			"Subagents that exited with an error or were aborted.",
		),

		storageWatcherLagSecondsDesc: d(
			"bridge_storage_watcher_lag_seconds",
			"Seconds between the most recent storage event timestamp "+
				"and now (last-observed gauge). Bridge-side; backend "+
				"publishes a richer histogram under "+
				"storage_watcher_lag_seconds for SLO p50/p99.",
		),

		statuslineLastReportAgeDesc: d(
			"statusline_last_report_age_seconds",
			"Seconds since ~/.claude/usage.json was last updated.",
		),
		statuslineFiveHourPctDesc: d(
			"statusline_five_hour_pct",
			"Most recently observed 5-hour usage percentage.",
		),
		statuslineSevenDayPctDesc: d(
			"statusline_seven_day_pct",
			"Most recently observed 7-day usage percentage.",
		),
	}
}

// Describe satisfies prometheus.Collector by emitting every Desc the
// collector publishes. Required by go-prometheus contract.
func (c *bridgeCollector) Describe(ch chan<- *prometheus.Desc) {
	ch <- c.uptimeSecondsDesc
	ch <- c.wsConnectedDesc
	ch <- c.wsReconnectsDesc
	ch <- c.wsDisconnectsDesc
	ch <- c.wsEventsForwardedDesc
	ch <- c.wsEventsDroppedDesc
	ch <- c.claudeSubprocessActiveDesc
	ch <- c.claudeSubprocessTotalDesc
	ch <- c.claudeLinesReadDesc
	ch <- c.claudeRateLimitHitsDesc
	ch <- c.claudeRateLimitWarningsDesc
	ch <- c.claudeRateLimitExceededDesc
	ch <- c.claudeAuthExpiredDesc
	ch <- c.claudeTotalCostUSDDesc
	ch <- c.subagentSpawnedDesc
	ch <- c.subagentCompletedDesc
	ch <- c.subagentFailedDesc
	ch <- c.storageWatcherLagSecondsDesc
	ch <- c.statuslineLastReportAgeDesc
	ch <- c.statuslineFiveHourPctDesc
	ch <- c.statuslineSevenDayPctDesc
}

// Collect snapshots every atomic counter/gauge and emits one sample
// each. Counters are emitted as Prometheus counters (monotonic);
// gauges as gauges. Cost is emitted in plain USD (not the *1000 storage
// trick) so dashboards don't have to undo the scaling — the conversion
// is just an int64→float64 division.
func (c *bridgeCollector) Collect(ch chan<- prometheus.Metric) {
	bv := promBridgeVersion
	hid := promHostID

	counter := func(desc *prometheus.Desc, val float64) {
		ch <- prometheus.MustNewConstMetric(desc, prometheus.CounterValue, val, bv, hid)
	}
	gauge := func(desc *prometheus.Desc, val float64) {
		ch <- prometheus.MustNewConstMetric(desc, prometheus.GaugeValue, val, bv, hid)
	}

	gauge(c.uptimeSecondsDesc, float64(BridgeUptimeSeconds.Load()))

	gauge(c.wsConnectedDesc, float64(WSConnected.Load()))
	counter(c.wsReconnectsDesc, float64(WSReconnects.Load()))
	counter(c.wsDisconnectsDesc, float64(WSDisconnects.Load()))
	counter(c.wsEventsForwardedDesc, float64(WSEventsForwarded.Load()))
	counter(c.wsEventsDroppedDesc, float64(WSEventsDropped.Load()))

	gauge(c.claudeSubprocessActiveDesc, float64(ClaudeSubprocessActive.Load()))
	counter(c.claudeSubprocessTotalDesc, float64(ClaudeSubprocessTotal.Load()))
	counter(c.claudeLinesReadDesc, float64(ClaudeLinesRead.Load()))
	counter(c.claudeRateLimitHitsDesc, float64(ClaudeRateLimitHits.Load()))
	counter(c.claudeRateLimitWarningsDesc, float64(ClaudeRateLimitWarnings.Load()))
	counter(c.claudeRateLimitExceededDesc, float64(ClaudeRateLimitExceeded.Load()))
	counter(c.claudeAuthExpiredDesc, float64(ClaudeAuthExpired.Load()))
	counter(c.claudeTotalCostUSDDesc, float64(ClaudeTotalCostUSDx1000.Load())/1000.0)

	counter(c.subagentSpawnedDesc, float64(SubagentSpawnedTotal.Load()))
	counter(c.subagentCompletedDesc, float64(SubagentCompletedTotal.Load()))
	counter(c.subagentFailedDesc, float64(SubagentFailedTotal.Load()))

	gauge(c.storageWatcherLagSecondsDesc, float64(StorageWatcherLagSeconds.Load()))

	gauge(c.statuslineLastReportAgeDesc, float64(StatuslineLastReportAge.Load()))
	gauge(c.statuslineFiveHourPctDesc, float64(StatuslineFiveHourPct.Load()))
	gauge(c.statuslineSevenDayPctDesc, float64(StatuslineSevenDayPct.Load()))
}
