// Package statusline polls ~/.claude/usage.json and forwards usage
// telemetry from Claude Code's statusline pipeline to the backend.
//
// Two pieces collaborate:
//
//   - Watcher (this file) — periodic mod-time-gated poller that turns
//     each file change into a typed protocol.EventUsageReport delivered
//     to the supplied sink. The bridge's main loop (T0.5.13) wires the
//     sink to the WebSocket outbox; tests substitute an in-process
//     channel-backed sink.
//
//   - Installer (installer.go) — one-shot helper that drops the
//     embedded statusline.py script into ~/.claude/ and merge-safely
//     registers it in ~/.claude/settings.json so Claude Code begins
//     producing usage.json on every interactive render.
//
// The split mirrors docs/11_Bridge_Spec.md §8 verbatim. Empirical
// behaviour and the upstream rate_limits schema are documented in
// docs/claude-code-usage-tracking.md and docs/10_Production_Pivot_Spec.md
// §2.11 (the kritik tamamlayıcı that motivates this entire pipeline —
// stream-json's rate_limit_event carries no percentage so the
// statusline path is the only source of 5h/7d gauges).
package statusline

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"os"
	"time"

	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/config"
	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/protocol"
	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/telemetry"
)

// defaultPollEvery is used when StatuslineConfig.PollEvery is zero.
// Mirrors the documented 5s cadence in docs/11_Bridge_Spec.md §8.
const defaultPollEvery = 5 * time.Second

// UsageSink receives one EventUsageReport per observed mod-time
// transition of usage.json. Implementations must be non-blocking
// relative to the watcher's poll cadence — the watcher will not buffer
// or retry; a slow sink simply delays the next poll.
type UsageSink func(protocol.EventUsageReport)

// Watcher periodically stats the configured usage.json path and emits
// EventUsageReport whenever the file's mod-time advances. Stale
// detection (telemetry-only — no event) fires whenever the most
// recently observed mod-time is older than StatuslineConfig.StaleAfter.
type Watcher struct {
	cfg         *config.Config
	logger      *slog.Logger
	lastModTime time.Time
}

// NewWatcher constructs a Watcher bound to cfg and logger. The logger
// must be non-nil; a nil cfg is rejected by Run with a clear error
// rather than panicking on first poll.
func NewWatcher(cfg *config.Config, logger *slog.Logger) *Watcher {
	if logger == nil {
		logger = slog.Default()
	}
	return &Watcher{cfg: cfg, logger: logger}
}

// Run drives the polling loop until ctx is cancelled. When
// StatuslineConfig.Enabled is false this is a no-op that returns nil
// immediately — operators that disable the watcher in config still
// expect a clean shutdown path. Returns ctx.Err() on cancellation,
// otherwise nil is unreachable.
func (w *Watcher) Run(ctx context.Context, sink UsageSink) error {
	if w.cfg == nil {
		return errors.New("statusline: nil config")
	}
	if sink == nil {
		return errors.New("statusline: nil sink")
	}
	if !w.cfg.Statusline.Enabled {
		w.logger.Info("statusline watcher disabled by config")
		return nil
	}

	interval := w.cfg.Statusline.PollEvery
	if interval <= 0 {
		interval = defaultPollEvery
	}

	w.logger.Info(
		"statusline watcher starting",
		"path", w.cfg.Statusline.UsagePath,
		"poll_every", interval,
		"stale_after", w.cfg.Statusline.StaleAfter,
	)

	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-ticker.C:
			w.poll(sink)
		}
	}
}

// poll performs one stat+read+emit cycle. All failure modes are
// non-fatal — they update telemetry and (where unexpected) log at
// warn level, then return so the next tick can try again. The
// mod-time gate ensures we never re-emit unchanged usage data even
// though we do continue to refresh staleness telemetry on every tick.
func (w *Watcher) poll(sink UsageSink) {
	info, err := os.Stat(w.cfg.Statusline.UsagePath)
	if err != nil {
		w.refreshStaleAge(w.lastModTime)
		// os.IsNotExist is the common case before the user runs
		// Claude Code interactively for the first time — debug
		// level keeps logs quiet during onboarding.
		if os.IsNotExist(err) {
			w.logger.Debug("statusline usage.json not yet present", "path", w.cfg.Statusline.UsagePath)
			return
		}
		w.logger.Warn("statusline stat error", "path", w.cfg.Statusline.UsagePath, "err", err)
		return
	}

	modTime := info.ModTime()
	if !modTime.After(w.lastModTime) {
		// File unchanged since last poll — only refresh staleness.
		w.refreshStaleAge(modTime)
		return
	}
	w.lastModTime = modTime

	raw, err := os.ReadFile(w.cfg.Statusline.UsagePath)
	if err != nil {
		w.logger.Warn("statusline read error", "path", w.cfg.Statusline.UsagePath, "err", err)
		return
	}

	var u struct {
		FiveHourPct      int   `json:"five_hour_pct"`
		SevenDayPct      int   `json:"seven_day_pct"`
		FiveHourResetsAt int64 `json:"five_hour_resets_at"`
		SevenDayResetsAt int64 `json:"seven_day_resets_at"`
		TS               int64 `json:"ts"`
	}
	if err := json.Unmarshal(raw, &u); err != nil {
		w.logger.Warn("statusline json decode error", "path", w.cfg.Statusline.UsagePath, "err", err)
		return
	}

	telemetry.StatuslineFiveHourPct.Store(int64(u.FiveHourPct))
	telemetry.StatuslineSevenDayPct.Store(int64(u.SevenDayPct))
	// Prefer the script's embedded ts field (seconds since epoch) as
	// the staleness clock — it matches the moment Claude Code last
	// rendered the statusline, which is what the operator cares
	// about. Fall back to mod-time if ts is zero/missing.
	stalenessClock := modTime
	if u.TS > 0 {
		stalenessClock = time.Unix(u.TS, 0)
	}
	w.refreshStaleAge(stalenessClock)

	sink(protocol.EventUsageReport{
		FiveHourPct:      u.FiveHourPct,
		SevenDayPct:      u.SevenDayPct,
		FiveHourResetsAt: u.FiveHourResetsAt,
		SevenDayResetsAt: u.SevenDayResetsAt,
		ReportedAt:       u.TS,
	})

	w.logger.Debug(
		"statusline usage report emitted",
		"five_hour_pct", u.FiveHourPct,
		"seven_day_pct", u.SevenDayPct,
		"ts", u.TS,
	)
}

// refreshStaleAge updates StatuslineLastReportAge with the seconds
// elapsed since the supplied reference time. A zero reference is
// treated as "never observed" and clears the gauge to zero — that
// state is distinguishable from a fresh report by reading the
// FiveHour/SevenDay percentage gauges, which only get populated after
// the first successful decode.
func (w *Watcher) refreshStaleAge(ref time.Time) {
	if ref.IsZero() {
		telemetry.StatuslineLastReportAge.Store(0)
		return
	}
	age := time.Since(ref)
	if age < 0 {
		age = 0
	}
	telemetry.StatuslineLastReportAge.Store(int64(age.Seconds()))
}
