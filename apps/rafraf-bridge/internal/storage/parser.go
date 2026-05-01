// Package storage tails the Claude CLI's per-session JSONL log files under
// ~/.claude/projects/ and surfaces a small subset of the events it finds —
// the ones documented in docs/10_Production_Pivot_Spec.md §2.4 as having
// real product value (ai-title, pr-link, attachment.hook_*).
//
// parser.go contains the pure, side-effect-free decoders. Watcher.dispatch
// invokes them, but they are also exercised directly in watcher_test.go so
// schema regressions surface independently of the file-system plumbing.
//
// Storage JSONL is a different format from the stream-json the runner reads:
// keys are camelCase, lines may carry RafRaf-irrelevant types (queue-operation,
// permission-mode, file-history-snapshot, etc.) that we deliberately ignore.
package storage

import (
	"encoding/json"
	"fmt"
	"strings"

	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/protocol"
)

// rawAITitle mirrors the on-disk shape of an "ai-title" jsonl row. Only
// the two fields RafRaf surfaces are decoded; anything else is dropped.
type rawAITitle struct {
	SessionID string `json:"sessionId"`
	AITitle   string `json:"aiTitle"`
}

// rawPRLink mirrors the on-disk shape of a "pr-link" jsonl row. The schema
// is documented in the task brief and matches the entries the spike harvested
// from production sessions.
type rawPRLink struct {
	SessionID    string `json:"sessionId"`
	PRNumber     int    `json:"prNumber"`
	PRURL        string `json:"prUrl"`
	PRRepository string `json:"prRepository"`
	Timestamp    string `json:"ts"`
}

// rawAttachment mirrors an "attachment" jsonl row. Only attachments whose
// nested type starts with "hook_" survive the watcher filter — the rest are
// dropped silently.
type rawAttachment struct {
	SessionID  string `json:"sessionId"`
	Attachment struct {
		Type    string          `json:"type"`
		Payload json.RawMessage `json:"payload"`
	} `json:"attachment"`
}

// parseAITitle decodes a single jsonl line known to be of type "ai-title"
// into the wire-side EventStorageAITitle. Unmarshal failures bubble up so
// the caller can log/skip; missing fields are tolerated and surface as
// empty strings so partial data still reaches the backend (which is more
// defensive than dropping silently).
func parseAITitle(raw []byte) (protocol.EventStorageAITitle, error) {
	var r rawAITitle
	if err := json.Unmarshal(raw, &r); err != nil {
		return protocol.EventStorageAITitle{}, fmt.Errorf("storage: parse ai-title: %w", err)
	}
	return protocol.EventStorageAITitle{
		SessionID: r.SessionID,
		Title:     r.AITitle,
	}, nil
}

// parsePRLink decodes a single jsonl line known to be of type "pr-link".
// All fields are optional from the parser's perspective; the backend is
// the validation authority.
func parsePRLink(raw []byte) (protocol.EventStoragePRLink, error) {
	var r rawPRLink
	if err := json.Unmarshal(raw, &r); err != nil {
		return protocol.EventStoragePRLink{}, fmt.Errorf("storage: parse pr-link: %w", err)
	}
	return protocol.EventStoragePRLink{
		SessionID:    r.SessionID,
		PRNumber:     r.PRNumber,
		PRURL:        r.PRURL,
		PRRepository: r.PRRepository,
		Timestamp:    r.Timestamp,
	}, nil
}

// parseHookAttachment decodes an "attachment" jsonl line and returns the
// EventStorageHookAttachment payload only when the nested attachment.type
// starts with "hook_". When the prefix does not match the boolean return
// is false and the event must be skipped — this is the entire reason the
// filter lives in the parser instead of inline in dispatch (it keeps the
// decision point in one tested location).
func parseHookAttachment(raw []byte) (protocol.EventStorageHookAttachment, bool, error) {
	var r rawAttachment
	if err := json.Unmarshal(raw, &r); err != nil {
		return protocol.EventStorageHookAttachment{}, false, fmt.Errorf("storage: parse attachment: %w", err)
	}
	if !strings.HasPrefix(r.Attachment.Type, "hook_") {
		return protocol.EventStorageHookAttachment{}, false, nil
	}
	return protocol.EventStorageHookAttachment{
		SessionID:      r.SessionID,
		AttachmentType: r.Attachment.Type,
		Payload:        r.Attachment.Payload,
	}, true, nil
}
