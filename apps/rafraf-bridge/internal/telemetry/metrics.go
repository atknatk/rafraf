// Package telemetry exposes the bridge's runtime counters and gauges.
//
// Two surfaces are provided:
//
//  1. Native Go atomics (atomic.Int32 / atomic.Int64). Hot-path call sites
//     across ws/, claude/, statusline/, storage/ load and increment these
//     directly without going through the slower expvar lock — this matches
//     the behaviour of the spike at ~/Code/claude-teams-spike/bridge/main.go
//     where every Claude stream-JSON line increments a counter.
//
//  2. The expvar surface mounted on /debug/vars by StartMetricsServer.
//     The expvar variables defined here mirror the names from
//     docs/11_Bridge_Spec.md §9 verbatim so dashboards/alerts can be
//     written against the spec without translation. Atomic counters are
//     re-published as expvar.Func wrappers so /debug/vars sees a single,
//     consistent snapshot without us having to maintain two separate
//     write paths.
//
// New telemetry should be added in canonical Doc 11 §9 order.
package telemetry

import (
	"expvar"
	"fmt"
	"sync/atomic"
)

// ---- Section: bridge meta ---------------------------------------------------

// BridgeUptimeSeconds is the wall-clock seconds since process start. It is
// updated by the metrics goroutine in cmd/bridge once per tick — kept here as
// an atomic so the writer does not need to hold the expvar lock on every
// update.
var BridgeUptimeSeconds atomic.Int64

// BridgeVersion holds the build version string (semver or git short SHA).
// Set once at startup via SetBridgeVersion.
var bridgeVersion atomic.Pointer[string]

// SetBridgeVersion publishes the bridge build version. Safe to call once at
// startup; subsequent calls overwrite atomically.
func SetBridgeVersion(v string) {
	bridgeVersion.Store(&v)
}

// ---- Section: WebSocket -----------------------------------------------------

var (
	// WSConnected is 1 while the WebSocket session is up, 0 otherwise.
	WSConnected atomic.Int32
	// WSReconnects counts every successful (re)connect.
	WSReconnects atomic.Int64
	// WSDisconnects counts every observed disconnect.
	WSDisconnects atomic.Int64
	// WSEventsForwarded counts envelopes successfully written to the socket.
	WSEventsForwarded atomic.Int64
	// WSEventsDropped counts envelopes dropped because the outbox was full.
	WSEventsDropped atomic.Int64
)

// ---- Section: Claude subprocess ---------------------------------------------

var (
	// ClaudeSubprocessActive tracks the number of currently running claude
	// subprocesses (gauge). Incremented when Runner.Run starts, decremented
	// on exit (regardless of success/failure/abort).
	ClaudeSubprocessActive atomic.Int64
	// ClaudeSubprocessTotal counts every claude subprocess ever launched
	// by this bridge process (counter). Useful for sanity-checking
	// abort/restart loops in production.
	ClaudeSubprocessTotal atomic.Int64
	// ClaudeLinesRead counts stream-JSON lines read from claude stdout.
	ClaudeLinesRead atomic.Int64
	// ClaudeRateLimitHits is the legacy aggregate counter for any
	// rate_limit_event line observed (warning + exceeded). It remains for
	// backwards compatibility with code paths landed before T0.5.11; new
	// callers should prefer ClaudeRateLimitWarnings or
	// ClaudeRateLimitExceeded for finer-grained alerting.
	ClaudeRateLimitHits atomic.Int64
	// ClaudeRateLimitWarnings counts rate_limit_event lines whose status
	// field was "warning". Rises ahead of an exceeded event and feeds the
	// statusline yellow-band alarm.
	ClaudeRateLimitWarnings atomic.Int64
	// ClaudeRateLimitExceeded counts rate_limit_event lines whose status
	// indicates the quota window was exhausted. Drives the red-band alarm
	// and bridges/exceeded webhook.
	ClaudeRateLimitExceeded atomic.Int64
	// ClaudeAuthExpired counts how many times the bridge observed an
	// expired/invalid claude auth state (either at startup or via a
	// stream-JSON auth_expired frame).
	ClaudeAuthExpired atomic.Int64
	// ClaudeTotalCostUSDx1000 is the cumulative cost across every claude
	// session, expressed as USD * 1000 to keep the field an int64. The
	// claude CLI reports float64 dollars in its `result` frame; the
	// runner multiplies by 1000 + truncates before adding.
	ClaudeTotalCostUSDx1000 atomic.Int64
)

// AddClaudeCostUSD adds a float USD amount to the cumulative ClaudeTotalCostUSDx1000
// counter. Centralised so callers do not have to remember the *1000 scaling
// trick (which is easy to forget and hard to spot in code review).
func AddClaudeCostUSD(amount float64) {
	if amount <= 0 {
		return
	}
	ClaudeTotalCostUSDx1000.Add(int64(amount * 1000))
}

// ---- Section: V1.x Claude Subprocess Supervisor ----------------------------
//
// Three metrics track the supervisor layer (per spec §5.2):
//   - claude_supervisor_instances_total{state} — gauge per state.
//   - claude_supervisor_diagnostics_total — counter (fired diagnostics).
//   - claude_supervisor_self_heals_total{outcome} — counter per recovery outcome.
//
// The {state} / {outcome} fan-out is implemented via expvar.Map on the
// expvar surface (the bridge's existing pattern, see
// StorageWatcherEventsTotal). The Prometheus collector mirrors them with
// per-state / per-outcome label values.
var (
	// ClaudeSupervisorInstancesTotal is a per-state gauge keyed by the
	// supervisor State string. Mutated by the supervisor on every state
	// transition; emitted on /metrics with one sample per known state.
	ClaudeSupervisorInstancesTotal = expvar.NewMap("claude_supervisor_instances_total")
	// ClaudeSupervisorDiagnosticsTotal counts every diagnostic spawn
	// (regardless of outcome).
	ClaudeSupervisorDiagnosticsTotal atomic.Int64
	// ClaudeSupervisorSelfHealsTotal is a per-outcome counter
	// ("recovered", "failed", "rate_limited", "depth_capped"). Same
	// expvar.Map pattern as above.
	ClaudeSupervisorSelfHealsTotal = expvar.NewMap("claude_supervisor_self_heals_total")
)

// ---- Section: Subagent (Task tool) ------------------------------------------

var (
	// SubagentSpawnedTotal counts every subagent the parser observed
	// being spawned (one increment per Task tool invocation).
	SubagentSpawnedTotal atomic.Int64
	// SubagentCompletedTotal counts subagents that emitted a terminal
	// success result.
	SubagentCompletedTotal atomic.Int64
	// SubagentFailedTotal counts subagents that exited with an error,
	// were aborted, or hit a permission denial.
	SubagentFailedTotal atomic.Int64
)

// ---- Section: Storage watcher -----------------------------------------------

// StorageWatcherEventsTotal counts storage events the watcher dispatched
// to its sink, keyed by the event subtype ("ai-title", "pr-link",
// "attachment"). Per-key counters use expvar.Map so dispatch sites can
// label by event subtype without pre-declaring every value. Incremented
// in internal/storage on every recognised frame regardless of decode
// outcome so operators can spot a sudden drop in any one stream.
var StorageWatcherEventsTotal = expvar.NewMap("storage_watcher_events_total")

// StorageWatcherLagSeconds is the gauge of how far behind realtime the
// watcher is — i.e. seconds between the most recently observed event's
// own timestamp and wall-clock now. A high value indicates either
// fsnotify backpressure or a slow sink.
var StorageWatcherLagSeconds atomic.Int64

// ---- Section: Statusline (~/.claude/usage.json) -----------------------------

var (
	// StatuslineLastReportAge is the number of seconds since
	// ~/.claude/usage.json was last updated (gauge). Updated by the
	// statusline.Watcher on every poll regardless of whether the file
	// changed; staleness alarms can fire off this value.
	StatuslineLastReportAge atomic.Int64
	// StatuslineFiveHourPct is the most recently observed 5-hour usage
	// percentage from ~/.claude/usage.json (gauge, 0–100).
	StatuslineFiveHourPct atomic.Int64
	// StatuslineSevenDayPct is the most recently observed 7-day usage
	// percentage from ~/.claude/usage.json (gauge, 0–100).
	StatuslineSevenDayPct atomic.Int64
)

// ---- expvar publication -----------------------------------------------------

// publish wires every atomic counter above into the package-level expvar
// registry under its canonical Doc 11 §9 name. Done in init so that the
// /debug/vars endpoint mounted by StartMetricsServer always exposes the
// full surface even if cmd/bridge has not yet bumped any counter.
//
// Using expvar.Publish(name, expvar.Func(...)) — rather than allocating a
// dedicated expvar.Int and dual-writing — keeps the hot path lock-free
// and guarantees the expvar snapshot is consistent with what the call
// site just stored.
func init() {
	expvar.Publish("bridge_uptime_seconds", expvar.Func(func() any { return BridgeUptimeSeconds.Load() }))
	expvar.Publish("bridge_version", expvar.Func(func() any {
		if p := bridgeVersion.Load(); p != nil {
			return *p
		}
		return ""
	}))

	expvar.Publish("ws_connected", expvar.Func(func() any { return int64(WSConnected.Load()) }))
	expvar.Publish("ws_reconnects_total", expvar.Func(func() any { return WSReconnects.Load() }))
	expvar.Publish("ws_disconnects_total", expvar.Func(func() any { return WSDisconnects.Load() }))
	expvar.Publish("ws_events_forwarded_total", expvar.Func(func() any { return WSEventsForwarded.Load() }))
	expvar.Publish("ws_events_dropped_total", expvar.Func(func() any { return WSEventsDropped.Load() }))

	expvar.Publish("claude_subprocess_active", expvar.Func(func() any { return ClaudeSubprocessActive.Load() }))
	expvar.Publish("claude_subprocess_total", expvar.Func(func() any { return ClaudeSubprocessTotal.Load() }))
	expvar.Publish("claude_stream_lines_read_total", expvar.Func(func() any { return ClaudeLinesRead.Load() }))
	expvar.Publish("claude_rate_limit_hits_total", expvar.Func(func() any { return ClaudeRateLimitHits.Load() }))
	expvar.Publish("claude_rate_limit_warnings_total", expvar.Func(func() any { return ClaudeRateLimitWarnings.Load() }))
	expvar.Publish("claude_rate_limit_exceeded_total", expvar.Func(func() any { return ClaudeRateLimitExceeded.Load() }))
	expvar.Publish("claude_auth_expired_total", expvar.Func(func() any { return ClaudeAuthExpired.Load() }))
	expvar.Publish("claude_total_cost_usd_x1000", expvar.Func(func() any { return ClaudeTotalCostUSDx1000.Load() }))
	expvar.Publish("claude_supervisor_diagnostics_total", expvar.Func(func() any { return ClaudeSupervisorDiagnosticsTotal.Load() }))

	expvar.Publish("subagent_spawned_total", expvar.Func(func() any { return SubagentSpawnedTotal.Load() }))
	expvar.Publish("subagent_completed_total", expvar.Func(func() any { return SubagentCompletedTotal.Load() }))
	expvar.Publish("subagent_failed_total", expvar.Func(func() any { return SubagentFailedTotal.Load() }))

	expvar.Publish("storage_watcher_lag_seconds", expvar.Func(func() any { return StorageWatcherLagSeconds.Load() }))

	expvar.Publish("statusline_last_report_age_seconds", expvar.Func(func() any { return StatuslineLastReportAge.Load() }))
	expvar.Publish("statusline_five_hour_pct", expvar.Func(func() any { return StatuslineFiveHourPct.Load() }))
	expvar.Publish("statusline_seven_day_pct", expvar.Func(func() any { return StatuslineSevenDayPct.Load() }))
}

// FormatMetricsLine produces the single-line stderr summary that the bridge
// prints every 15 seconds. Centralising the format string here keeps the
// metrics goroutine in cmd/bridge thin and lets us extend the catalogue
// without touching main.
func FormatMetricsLine() string {
	return fmt.Sprintf(
		"[metrics] connected=%d reconnects=%d disconnects=%d events=%d dropped=%d "+
			"claude_active=%d claude_total=%d claude_lines=%d "+
			"rate_limit_hits=%d rate_limit_warn=%d rate_limit_exceeded=%d auth_expired=%d cost_usd_x1000=%d "+
			"subagent_spawned=%d subagent_done=%d subagent_failed=%d "+
			"statusline_age=%d statusline_5h=%d statusline_7d=%d "+
			"storage_lag=%d",
		WSConnected.Load(),
		WSReconnects.Load(),
		WSDisconnects.Load(),
		WSEventsForwarded.Load(),
		WSEventsDropped.Load(),
		ClaudeSubprocessActive.Load(),
		ClaudeSubprocessTotal.Load(),
		ClaudeLinesRead.Load(),
		ClaudeRateLimitHits.Load(),
		ClaudeRateLimitWarnings.Load(),
		ClaudeRateLimitExceeded.Load(),
		ClaudeAuthExpired.Load(),
		ClaudeTotalCostUSDx1000.Load(),
		SubagentSpawnedTotal.Load(),
		SubagentCompletedTotal.Load(),
		SubagentFailedTotal.Load(),
		StatuslineLastReportAge.Load(),
		StatuslineFiveHourPct.Load(),
		StatuslineSevenDayPct.Load(),
		StorageWatcherLagSeconds.Load(),
	)
}
