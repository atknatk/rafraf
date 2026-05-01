// Package protocol defines the wire envelope shared between the bridge and
// the control plane. T0.5.2 imports the bare struct from the spike; the full
// command/event catalogue (CommandClaudeRun, EventSession*, ...) described in
// docs/11_Bridge_Spec.md §3.3 lands in T0.5.4.
package protocol

import (
	"encoding/json"
	"time"

	"github.com/google/uuid"
)

// Envelope is the canonical wire frame exchanged between the bridge and the
// control plane. Field tags match docs/11_Bridge_Spec.md §3.3 / §4.8 of the
// project plan.
type Envelope struct {
	Type          string          `json:"type"`
	ID            string          `json:"id"`
	TS            string          `json:"ts"`
	CorrelationID string          `json:"correlation_id,omitempty"`
	Target        string          `json:"target,omitempty"`
	Payload       json.RawMessage `json:"payload,omitempty"`
}

// NewID returns a fresh UUID string for use as Envelope.ID.
//
// The spike used UUIDv4; the spec calls for UUIDv7 but that migration is
// deferred to T0.5.4 where the message catalogue lands.
func NewID() string { return uuid.NewString() }

// NowISO returns the current UTC time formatted as RFC3339 with nanosecond
// precision, matching what the spike emitted.
func NowISO() string { return time.Now().UTC().Format(time.RFC3339Nano) }

// MustJSON marshals v to json.RawMessage, returning an empty payload on
// failure. This mirrors the spike helper; later tasks may swap to a
// fail-loud variant once we have a logger plumbed through.
func MustJSON(v any) json.RawMessage {
	b, err := json.Marshal(v)
	if err != nil {
		return json.RawMessage("{}")
	}
	return b
}
