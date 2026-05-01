package telemetry_test

import (
	"bytes"
	"encoding/json"
	"strings"
	"testing"

	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/telemetry"
)

// TestNewLogger_LevelFiltering exercises every documented level + the
// "unknown -> info" fallback. We assert via the JSON output rather than
// reflecting on the handler so the test survives slog internal renames.
func TestNewLogger_LevelFiltering(t *testing.T) {
	t.Parallel()

	cases := []struct {
		name     string
		level    string
		emit     []string // method names to call on the logger
		wantHas  []string // substrings that MUST be in output
		wantMiss []string // substrings that MUST NOT be in output
	}{
		{
			name:     "debug emits all",
			level:    "debug",
			emit:     []string{"debug", "info", "warn", "error"},
			wantHas:  []string{`"level":"DEBUG"`, `"level":"INFO"`, `"level":"WARN"`, `"level":"ERROR"`},
			wantMiss: nil,
		},
		{
			name:     "info filters debug",
			level:    "info",
			emit:     []string{"debug", "info", "warn", "error"},
			wantHas:  []string{`"level":"INFO"`, `"level":"WARN"`, `"level":"ERROR"`},
			wantMiss: []string{`"level":"DEBUG"`},
		},
		{
			name:     "warn filters debug+info",
			level:    "warn",
			emit:     []string{"debug", "info", "warn", "error"},
			wantHas:  []string{`"level":"WARN"`, `"level":"ERROR"`},
			wantMiss: []string{`"level":"DEBUG"`, `"level":"INFO"`},
		},
		{
			name:     "error keeps only error",
			level:    "error",
			emit:     []string{"debug", "info", "warn", "error"},
			wantHas:  []string{`"level":"ERROR"`},
			wantMiss: []string{`"level":"DEBUG"`, `"level":"INFO"`, `"level":"WARN"`},
		},
		{
			name:     "unknown falls back to info",
			level:    "verbose", // not a real level
			emit:     []string{"debug", "info"},
			wantHas:  []string{`"level":"INFO"`},
			wantMiss: []string{`"level":"DEBUG"`},
		},
	}

	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			var buf bytes.Buffer
			logger := telemetry.NewLoggerWithWriter(tc.level, &buf)
			for _, m := range tc.emit {
				switch m {
				case "debug":
					logger.Debug("dbg-msg")
				case "info":
					logger.Info("inf-msg")
				case "warn":
					logger.Warn("wrn-msg")
				case "error":
					logger.Error("err-msg")
				}
			}

			out := buf.String()
			for _, want := range tc.wantHas {
				if !strings.Contains(out, want) {
					t.Errorf("output missing %q\nfull output:\n%s", want, out)
				}
			}
			for _, miss := range tc.wantMiss {
				if strings.Contains(out, miss) {
					t.Errorf("output unexpectedly contains %q\nfull output:\n%s", miss, out)
				}
			}
		})
	}
}

// TestNewLogger_JSONShape confirms the default handler is JSON, not text —
// downstream tooling (CloudWatch insights, jq pipelines) depends on that.
func TestNewLogger_JSONShape(t *testing.T) {
	t.Parallel()

	var buf bytes.Buffer
	logger := telemetry.NewLoggerWithWriter("info", &buf)
	logger.Info("hello", "key", "value")

	var record map[string]any
	if err := json.Unmarshal(bytes.TrimSpace(buf.Bytes()), &record); err != nil {
		t.Fatalf("output is not valid JSON: %v\nraw: %q", err, buf.String())
	}
	if record["msg"] != "hello" {
		t.Errorf("msg = %v, want hello", record["msg"])
	}
	if record["key"] != "value" {
		t.Errorf("key = %v, want value", record["key"])
	}
	if record["level"] != "INFO" {
		t.Errorf("level = %v, want INFO", record["level"])
	}
}

// TestNewLogger_StderrConstructorDoesNotPanic guards the convenience
// constructor that targets os.Stderr. We cannot easily intercept stderr
// without complicating the test, so we just assert it returns a non-nil
// logger and accepts a write call.
func TestNewLogger_StderrConstructorDoesNotPanic(t *testing.T) {
	t.Parallel()

	logger := telemetry.NewLogger("warn")
	if logger == nil {
		t.Fatal("NewLogger returned nil")
	}
	// Calling Warn on a real stderr-backed logger is safe in tests; the
	// goal is only to confirm no panic in the construction/dispatch path.
	logger.Warn("stderr-smoke")
}
