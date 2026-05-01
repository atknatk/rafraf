// Package claude wraps the `claude -p --output-format stream-json`
// subprocess. T0.5.2 only ports the spike implementation; the richer
// EventSink interface, env injection and abort semantics described in
// docs/11_Bridge_Spec.md §3.4 land in T0.5.5.
package claude

import "encoding/json"

// StreamEvent mirrors the lines emitted by `claude -p --output-format
// stream-json --verbose`. The Raw field carries the original byte slice so
// downstream consumers can re-marshal without losing fields not modelled
// here.
type StreamEvent struct {
	Type      string          `json:"type"`
	Subtype   string          `json:"subtype,omitempty"`
	SessionID string          `json:"session_id,omitempty"`
	UUID      string          `json:"uuid,omitempty"`
	Raw       json.RawMessage `json:"-"` // full original line
}
