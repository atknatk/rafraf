package statusline_test

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"log/slog"
	"os"
	"path/filepath"
	"sync"
	"testing"
	"time"

	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/config"
	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/protocol"
	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/statusline"
	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/telemetry"
)

// testCfg builds a StatuslineConfig pointing at usagePath with the
// short polling cadence we use throughout the tests below. The
// surrounding *config.Config is intentionally minimal — only the
// Statusline sub-struct matters to NewWatcher.
func testCfg(usagePath string, enabled bool) *config.Config {
	return &config.Config{
		Statusline: config.StatuslineConfig{
			Enabled:    enabled,
			UsagePath:  usagePath,
			PollEvery:  20 * time.Millisecond,
			StaleAfter: time.Hour,
		},
	}
}

// captureSink wraps a slice of received events behind a mutex so tests
// can inspect emission counts and the most recent payload without
// racing the watcher goroutine.
type captureSink struct {
	mu     sync.Mutex
	events []protocol.EventUsageReport
	cond   *sync.Cond
}

func newCaptureSink() *captureSink {
	s := &captureSink{}
	s.cond = sync.NewCond(&s.mu)
	return s
}

func (s *captureSink) Sink() statusline.UsageSink {
	return func(ev protocol.EventUsageReport) {
		s.mu.Lock()
		s.events = append(s.events, ev)
		s.cond.Broadcast()
		s.mu.Unlock()
	}
}

// waitFor blocks until len(events) >= want or the deadline elapses.
// Returns the snapshot of received events at the time the condition
// was satisfied (or the deadline hit).
func (s *captureSink) waitFor(t *testing.T, want int, deadline time.Duration) []protocol.EventUsageReport {
	t.Helper()
	timer := time.NewTimer(deadline)
	defer timer.Stop()
	done := make(chan struct{})
	var snapshot []protocol.EventUsageReport
	go func() {
		s.mu.Lock()
		defer s.mu.Unlock()
		for len(s.events) < want {
			s.cond.Wait()
		}
		snapshot = append(snapshot, s.events...)
		close(done)
	}()
	select {
	case <-done:
		return snapshot
	case <-timer.C:
		// Take a final snapshot under the lock and broadcast to
		// release the waiter goroutine cleanly so it does not leak
		// past the test.
		s.mu.Lock()
		snapshot = append(snapshot, s.events...)
		s.cond.Broadcast()
		s.mu.Unlock()
		<-done
		return snapshot
	}
}

// writeUsageJSON serialises the supplied payload to usagePath and
// then bumps mod-time slightly to defeat low-resolution filesystems
// (some macOS builds report mod-time at 1s granularity).
func writeUsageJSON(t *testing.T, usagePath string, payload map[string]interface{}) {
	t.Helper()
	raw, err := json.Marshal(payload)
	if err != nil {
		t.Fatalf("marshal usage: %v", err)
	}
	if err := os.WriteFile(usagePath, raw, 0o644); err != nil {
		t.Fatalf("write usage.json: %v", err)
	}
	// Force a future mod-time so the watcher's gate sees a change
	// even when the polling cadence is faster than the FS resolution.
	future := time.Now().Add(2 * time.Second)
	if err := os.Chtimes(usagePath, future, future); err != nil {
		t.Fatalf("chtimes usage.json: %v", err)
	}
}

func TestWatcher_EmitOnChange(t *testing.T) {
	t.Parallel()
	dir := t.TempDir()
	usagePath := filepath.Join(dir, "usage.json")

	cfg := testCfg(usagePath, true)
	sink := newCaptureSink()

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	w := statusline.NewWatcher(cfg, slog.New(slog.NewTextHandler(io.Discard, nil)))
	go func() { _ = w.Run(ctx, sink.Sink()) }()

	// Brief warm-up so the first tick fires before we write.
	time.Sleep(40 * time.Millisecond)

	ts := time.Now().Unix()
	writeUsageJSON(t, usagePath, map[string]interface{}{
		"five_hour_pct":       85,
		"seven_day_pct":       22,
		"five_hour_resets_at": int64(1777657800),
		"seven_day_resets_at": int64(1778166000),
		"ts":                  ts,
	})

	events := sink.waitFor(t, 1, 1*time.Second)
	if len(events) == 0 {
		t.Fatal("no event received within deadline")
	}
	got := events[0]
	if got.FiveHourPct != 85 {
		t.Errorf("FiveHourPct = %d, want 85", got.FiveHourPct)
	}
	if got.SevenDayPct != 22 {
		t.Errorf("SevenDayPct = %d, want 22", got.SevenDayPct)
	}
	if got.FiveHourResetsAt != 1777657800 {
		t.Errorf("FiveHourResetsAt = %d, want 1777657800", got.FiveHourResetsAt)
	}
	if got.SevenDayResetsAt != 1778166000 {
		t.Errorf("SevenDayResetsAt = %d, want 1778166000", got.SevenDayResetsAt)
	}
	if got.ReportedAt != ts {
		t.Errorf("ReportedAt = %d, want %d", got.ReportedAt, ts)
	}

	// Telemetry counters should reflect the latest emission.
	if got := telemetry.StatuslineFiveHourPct.Load(); got != 85 {
		t.Errorf("StatuslineFiveHourPct = %d, want 85", got)
	}
	if got := telemetry.StatuslineSevenDayPct.Load(); got != 22 {
		t.Errorf("StatuslineSevenDayPct = %d, want 22", got)
	}
}

func TestWatcher_NoEmitWhenUnchanged(t *testing.T) {
	t.Parallel()
	dir := t.TempDir()
	usagePath := filepath.Join(dir, "usage.json")

	cfg := testCfg(usagePath, true)
	sink := newCaptureSink()

	// Pre-write usage.json so the very first tick consumes it. We
	// then expect no further events for the remainder of the run.
	writeUsageJSON(t, usagePath, map[string]interface{}{
		"five_hour_pct":       40,
		"seven_day_pct":       10,
		"five_hour_resets_at": int64(0),
		"seven_day_resets_at": int64(0),
		"ts":                  time.Now().Unix(),
	})

	ctx, cancel := context.WithTimeout(context.Background(), 400*time.Millisecond)
	defer cancel()

	w := statusline.NewWatcher(cfg, slog.New(slog.NewTextHandler(io.Discard, nil)))
	done := make(chan struct{})
	go func() {
		_ = w.Run(ctx, sink.Sink())
		close(done)
	}()
	<-done

	sink.mu.Lock()
	count := len(sink.events)
	sink.mu.Unlock()
	if count != 1 {
		t.Fatalf("got %d events across many polls, want exactly 1 (mod-time gate)", count)
	}
}

func TestWatcher_DisabledNoOp(t *testing.T) {
	t.Parallel()
	dir := t.TempDir()
	usagePath := filepath.Join(dir, "usage.json")

	cfg := testCfg(usagePath, false) // disabled
	sink := newCaptureSink()

	// Even with usage.json present, a disabled watcher must not emit.
	writeUsageJSON(t, usagePath, map[string]interface{}{
		"five_hour_pct":       99,
		"seven_day_pct":       99,
		"five_hour_resets_at": int64(0),
		"seven_day_resets_at": int64(0),
		"ts":                  time.Now().Unix(),
	})

	ctx, cancel := context.WithTimeout(context.Background(), 200*time.Millisecond)
	defer cancel()

	w := statusline.NewWatcher(cfg, slog.New(slog.NewTextHandler(io.Discard, nil)))
	if err := w.Run(ctx, sink.Sink()); err != nil {
		t.Fatalf("Run() returned error for disabled watcher: %v", err)
	}

	sink.mu.Lock()
	count := len(sink.events)
	sink.mu.Unlock()
	if count != 0 {
		t.Errorf("disabled watcher emitted %d events, want 0", count)
	}
}

func TestWatcher_MalformedJSONLogged(t *testing.T) {
	t.Parallel()
	dir := t.TempDir()
	usagePath := filepath.Join(dir, "usage.json")

	cfg := testCfg(usagePath, true)
	sink := newCaptureSink()

	// Capture warn-level slog output so we can assert the error path
	// surfaces a structured log entry rather than panicking or
	// silently dropping the bad input.
	var buf bytes.Buffer
	handler := slog.NewTextHandler(&buf, &slog.HandlerOptions{Level: slog.LevelDebug})

	if err := os.WriteFile(usagePath, []byte("not-json-at-all"), 0o644); err != nil {
		t.Fatalf("write garbage usage.json: %v", err)
	}
	future := time.Now().Add(2 * time.Second)
	if err := os.Chtimes(usagePath, future, future); err != nil {
		t.Fatalf("chtimes: %v", err)
	}

	ctx, cancel := context.WithTimeout(context.Background(), 300*time.Millisecond)
	defer cancel()

	w := statusline.NewWatcher(cfg, slog.New(handler))
	_ = w.Run(ctx, sink.Sink())

	sink.mu.Lock()
	count := len(sink.events)
	sink.mu.Unlock()
	if count != 0 {
		t.Errorf("malformed JSON produced %d events, want 0", count)
	}
	if !bytes.Contains(buf.Bytes(), []byte("statusline json decode error")) {
		t.Errorf("expected decode-error log entry, got:\n%s", buf.String())
	}
}

func TestWatcher_NilConfigReturnsError(t *testing.T) {
	t.Parallel()
	w := statusline.NewWatcher(nil, slog.New(slog.NewTextHandler(io.Discard, nil)))
	err := w.Run(context.Background(), func(protocol.EventUsageReport) {})
	if err == nil {
		t.Fatal("expected error from Run() with nil config")
	}
}

func TestWatcher_NilSinkReturnsError(t *testing.T) {
	t.Parallel()
	cfg := testCfg("/tmp/does-not-matter", true)
	w := statusline.NewWatcher(cfg, slog.New(slog.NewTextHandler(io.Discard, nil)))
	err := w.Run(context.Background(), nil)
	if err == nil {
		t.Fatal("expected error from Run() with nil sink")
	}
}

func TestWatcher_StaleTelemetryRefreshedWhenMissing(t *testing.T) {
	t.Parallel()
	dir := t.TempDir()
	usagePath := filepath.Join(dir, "usage.json") // never created
	cfg := testCfg(usagePath, true)
	sink := newCaptureSink()

	// Reset the telemetry gauge so we can observe the no-op path
	// below leaves it at zero (never-observed marker).
	telemetry.StatuslineLastReportAge.Store(-1)

	ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
	defer cancel()

	w := statusline.NewWatcher(cfg, slog.New(slog.NewTextHandler(io.Discard, nil)))
	_ = w.Run(ctx, sink.Sink())

	if got := telemetry.StatuslineLastReportAge.Load(); got != 0 {
		t.Errorf("StatuslineLastReportAge = %d, want 0 (never observed)", got)
	}
}
