// Logging foundation for the bridge runtime.
//
// Per docs/11_Bridge_Spec.md §9 and the [telemetry] block in §12.1, the
// bridge ships an slog.Logger configured from TelemetryConfig.LogLevel.
// Sub-packages (claude, ws, storage, statusline) accept *slog.Logger via
// dependency injection so tests can swap in a discard handler.
//
// Output is JSON on stderr by default; the bridge launchd unit captures
// stderr to ~/Library/Logs/rafraf-bridge/bridge.log per Doc 11 §12.
// The optional second parameter to NewLoggerWithWriter lets cmd/bridge
// fan out to a log file in addition to stderr in T0.5.13.
package telemetry

import (
	"io"
	"log/slog"
	"os"
)

// NewLogger constructs an slog.Logger with the configured level. Output is
// JSON on stderr. Unknown level strings fall back to "info" rather than
// panicking — the config layer validates the enum, but this fallback keeps
// NewLogger safe for ad-hoc callers (tests, recovery paths).
func NewLogger(level string) *slog.Logger {
	return NewLoggerWithWriter(level, os.Stderr)
}

// NewLoggerWithWriter is the test/extensibility hook for NewLogger. It
// writes JSON-formatted records at the requested level to w. Passing
// io.Discard yields a silent logger suitable for unit tests.
func NewLoggerWithWriter(level string, w io.Writer) *slog.Logger {
	lvl := parseLevel(level)
	handler := slog.NewJSONHandler(w, &slog.HandlerOptions{Level: lvl})
	return slog.New(handler)
}

// parseLevel maps the four operator-facing level names to slog levels.
// Anything else returns slog.LevelInfo.
func parseLevel(level string) slog.Level {
	switch level {
	case "debug":
		return slog.LevelDebug
	case "info":
		return slog.LevelInfo
	case "warn":
		return slog.LevelWarn
	case "error":
		return slog.LevelError
	default:
		return slog.LevelInfo
	}
}
