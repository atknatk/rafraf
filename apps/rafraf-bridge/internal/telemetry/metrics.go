// Package telemetry exposes process-wide atomic counters used by the bridge
// runtime. The counters mirror those introduced in the spike
// (~/Code/claude-teams-spike/bridge/main.go) but are now exported so that
// other packages (ws, claude, cmd/bridge) can update them without sharing a
// package boundary.
//
// The full expvar/OTel surface described in docs/11_Bridge_Spec.md §9 will
// land in later tasks (T0.5.11+); for T0.5.2 we keep the lean atomic set so
// behavior is identical to the spike.
package telemetry

import (
	"expvar"
	"fmt"
	"sync/atomic"
)

// Atomic counters. Names mirror docs/11_Bridge_Spec.md §9 where reasonable.
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
	// ClaudeRateLimitHits counts rate_limit_event lines observed.
	ClaudeRateLimitHits atomic.Int64
)

// expvar surfaces. Per docs/11_Bridge_Spec.md §9, these are exported for the
// /debug/vars endpoint that T0.5.11 will expose. Per-key counters use
// expvar.Map so the dispatch site can label by event subtype without
// pre-declaring every value.
var (
	// StorageWatcherEventsTotal counts storage events the watcher dispatched
	// to its sink, keyed by the event subtype ("ai-title", "pr-link",
	// "attachment"). Incremented in internal/storage on every recognised
	// frame regardless of decode outcome so operators can spot a sudden
	// drop in any one stream.
	StorageWatcherEventsTotal = expvar.NewMap("storage_watcher_events_total")
)

// FormatMetricsLine produces the single-line stderr summary that the bridge
// prints every 15 seconds. Centralising the format string here keeps the
// metrics goroutine in cmd/bridge thin and lets us extend the catalogue
// without touching main.
func FormatMetricsLine() string {
	return fmt.Sprintf(
		"[metrics] connected=%d reconnects=%d disconnects=%d events=%d dropped=%d claude_active=%d claude_total=%d claude_lines=%d rate_limit_hits=%d",
		WSConnected.Load(),
		WSReconnects.Load(),
		WSDisconnects.Load(),
		WSEventsForwarded.Load(),
		WSEventsDropped.Load(),
		ClaudeSubprocessActive.Load(),
		ClaudeSubprocessTotal.Load(),
		ClaudeLinesRead.Load(),
		ClaudeRateLimitHits.Load(),
	)
}
