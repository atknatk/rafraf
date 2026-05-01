package claude

import (
	"bufio"
	"io"
	"log/slog"

	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/telemetry"
)

// Parser reads stream-json output from a `claude -p` subprocess one line
// at a time. The T0.5.5 implementation drains the reader and updates
// line-count telemetry; T0.5.6 will fill out full JSON dispatch into the
// EventSink (assistant / user / stream / task_* / hook_* / result frames).
//
// The shape is fixed so T0.5.6 only changes Parse's body, not its
// signature or any caller.
type Parser struct {
	sink   EventSink
	logger *slog.Logger
}

// NewParser constructs a Parser bound to the given sink. Sink may be nil
// during T0.5.5 since no callbacks are invoked yet; T0.5.6 will require
// a non-nil sink.
func NewParser(sink EventSink, logger *slog.Logger) *Parser {
	if logger == nil {
		logger = slog.Default()
	}
	return &Parser{sink: sink, logger: logger}
}

// Parse reads stdout line-by-line until EOF or the underlying reader
// errors. T0.5.5 only counts lines; T0.5.6 will JSON-decode each line
// and dispatch into p.sink based on the `type`/`subtype` discriminators
// described in docs/11_Bridge_Spec.md §6.
func (p *Parser) Parse(stdout io.Reader) error {
	scanner := bufio.NewScanner(stdout)
	scanner.Buffer(make([]byte, stdoutInitialBufSize), stdoutMaxLineSize)
	for scanner.Scan() {
		// Bytes() returns a slice valid only until the next Scan; the
		// dispatch path in T0.5.6 will copy when forwarding into typed
		// payloads. For the placeholder we only need the length.
		_ = scanner.Bytes()
		telemetry.ClaudeLinesRead.Add(1)
	}
	return scanner.Err()
}
