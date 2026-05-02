// Package protocol — typed builders.
//
// These helpers wrap Envelope construction with auto-generated ID + timestamp
// + payload marshalling. They mirror the Python `build_claude_stream_*_message`
// pattern in apps/agent/agent/core/protocol.py so the call sites read the
// same in Go and Python.
//
// All builders return (Envelope, error). Marshalling can only fail if a
// payload field contains a value the encoding/json package cannot serialise
// (e.g. cyclic graph, channel, function); callers should treat the error as
// a programming bug rather than a runtime condition.
package protocol

import (
	"encoding/json"
	"fmt"
)

// newEvent is the shared core helper. Type-specific wrappers below pin the
// `typ` argument to the right constant so callers cannot drift.
func newEvent(typ, target, correlationID string, payload any) (Envelope, error) {
	raw, err := json.Marshal(payload)
	if err != nil {
		return Envelope{}, fmt.Errorf("protocol: marshal %s payload: %w", typ, err)
	}
	return Envelope{
		Type:          typ,
		ID:            NewID(),
		TS:            NowISO(),
		CorrelationID: correlationID,
		Target:        target,
		Payload:       raw,
	}, nil
}

// ---------------------------------------------------------------------------
// Inbound builders — primarily used by tests and the local CLI replay path.
// ---------------------------------------------------------------------------

// NewCommandClaudeRun builds a `command.claude.run` envelope.
func NewCommandClaudeRun(target, correlationID string, payload CommandClaudeRun) (Envelope, error) {
	return newEvent(TypeCommandClaudeRun, target, correlationID, payload)
}

// NewCommandClaudeAbort builds a `command.claude.abort` envelope.
func NewCommandClaudeAbort(target, correlationID string, payload CommandClaudeAbort) (Envelope, error) {
	return newEvent(TypeCommandClaudeAbort, target, correlationID, payload)
}

// NewCommandClaudePermissionAllow builds a
// `command.claude.permission.allow` envelope. The bridge's inbound
// dispatcher routes these to the permission Broker, which resolves the
// matching in-flight PreToolUse hook with an Allow decision. The
// correlation_id should mirror the originating command.claude.run rpc
// id so future audit tooling can stitch the round-trip back together;
// the broker itself routes by the payload's RequestID.
func NewCommandClaudePermissionAllow(target, correlationID string, payload CommandClaudePermissionDecision) (Envelope, error) {
	return newEvent(TypeCommandClaudePermissionAllow, target, correlationID, payload)
}

// NewCommandClaudePermissionDeny builds a
// `command.claude.permission.deny` envelope. Symmetric to
// NewCommandClaudePermissionAllow — fired when the iOS user taps
// "Reddet" or the iOS countdown expires (auto-deny).
func NewCommandClaudePermissionDeny(target, correlationID string, payload CommandClaudePermissionDecision) (Envelope, error) {
	return newEvent(TypeCommandClaudePermissionDeny, target, correlationID, payload)
}

// ---------------------------------------------------------------------------
// Outbound — Session events.
// ---------------------------------------------------------------------------

// NewEventSessionInit builds an `event.session.init` envelope.
func NewEventSessionInit(target, correlationID string, payload EventSessionInit) (Envelope, error) {
	return newEvent(TypeEventSessionInit, target, correlationID, payload)
}

// NewEventSessionAssistant builds an `event.session.assistant` envelope.
func NewEventSessionAssistant(target, correlationID string, payload EventSessionAssistant) (Envelope, error) {
	return newEvent(TypeEventSessionAssistant, target, correlationID, payload)
}

// NewEventSessionUser builds an `event.session.user` envelope.
func NewEventSessionUser(target, correlationID string, payload EventSessionUser) (Envelope, error) {
	return newEvent(TypeEventSessionUser, target, correlationID, payload)
}

// NewEventSessionStream builds an `event.session.stream` envelope.
func NewEventSessionStream(target, correlationID string, payload EventSessionStream) (Envelope, error) {
	return newEvent(TypeEventSessionStream, target, correlationID, payload)
}

// NewEventSessionTaskStarted builds an `event.session.task_started` envelope.
func NewEventSessionTaskStarted(target, correlationID string, payload EventSessionTaskStarted) (Envelope, error) {
	return newEvent(TypeEventSessionTaskStarted, target, correlationID, payload)
}

// NewEventSessionTaskProgress builds an `event.session.task_progress` envelope.
func NewEventSessionTaskProgress(target, correlationID string, payload EventSessionTaskProgress) (Envelope, error) {
	return newEvent(TypeEventSessionTaskProgress, target, correlationID, payload)
}

// NewEventSessionTaskNotification builds an `event.session.task_notification`
// envelope.
func NewEventSessionTaskNotification(target, correlationID string, payload EventSessionTaskNotification) (Envelope, error) {
	return newEvent(TypeEventSessionTaskNotification, target, correlationID, payload)
}

// NewEventSessionRateLimit builds an `event.session.rate_limit` envelope.
func NewEventSessionRateLimit(target, correlationID string, payload EventSessionRateLimit) (Envelope, error) {
	return newEvent(TypeEventSessionRateLimit, target, correlationID, payload)
}

// NewEventSessionResult builds an `event.session.result` envelope.
func NewEventSessionResult(target, correlationID string, payload EventSessionResult) (Envelope, error) {
	return newEvent(TypeEventSessionResult, target, correlationID, payload)
}

// NewEventSessionHookStarted builds an `event.session.hook_started` envelope.
func NewEventSessionHookStarted(target, correlationID string, payload EventSessionHookStarted) (Envelope, error) {
	return newEvent(TypeEventSessionHookStarted, target, correlationID, payload)
}

// NewEventSessionHookResponse builds an `event.session.hook_response` envelope.
func NewEventSessionHookResponse(target, correlationID string, payload EventSessionHookResponse) (Envelope, error) {
	return newEvent(TypeEventSessionHookResponse, target, correlationID, payload)
}

// NewEventSessionPermissionRequest builds an
// `event.session.permission_request` envelope — the outbound side of
// the V1 PreToolUse permission flow. The correlation_id MUST be the
// originating command.claude.run rpc id so the backend orchestrator can
// route the question into the correct per-session subscriber queue;
// the payload's RequestID is the decision-correlation token reused by
// the inbound command.claude.permission.allow|deny RPC.
func NewEventSessionPermissionRequest(target, correlationID string, payload EventSessionPermissionRequest) (Envelope, error) {
	return newEvent(TypeEventSessionPermissionRequest, target, correlationID, payload)
}

// ---------------------------------------------------------------------------
// Outbound — Storage events.
// ---------------------------------------------------------------------------

// NewEventStorageAITitle builds an `event.storage.ai_title` envelope.
func NewEventStorageAITitle(target, correlationID string, payload EventStorageAITitle) (Envelope, error) {
	return newEvent(TypeEventStorageAITitle, target, correlationID, payload)
}

// NewEventStoragePRLink builds an `event.storage.pr_link` envelope.
func NewEventStoragePRLink(target, correlationID string, payload EventStoragePRLink) (Envelope, error) {
	return newEvent(TypeEventStoragePRLink, target, correlationID, payload)
}

// NewEventStorageHookAttachment builds an `event.storage.hook_attachment`
// envelope.
func NewEventStorageHookAttachment(target, correlationID string, payload EventStorageHookAttachment) (Envelope, error) {
	return newEvent(TypeEventStorageHookAttachment, target, correlationID, payload)
}

// ---------------------------------------------------------------------------
// Outbound — Statusline.
// ---------------------------------------------------------------------------

// NewEventUsageReport builds an `event.usage.report` envelope.
func NewEventUsageReport(target, correlationID string, payload EventUsageReport) (Envelope, error) {
	return newEvent(TypeEventUsageReport, target, correlationID, payload)
}

// ---------------------------------------------------------------------------
// Outbound — Bridge meta.
// ---------------------------------------------------------------------------

// NewEventBridgeAlive builds an `event.bridge.alive` envelope. Bridge meta
// events are unsolicited so correlation_id is rarely set; pass "" when the
// emitter has no correlated request id.
func NewEventBridgeAlive(target, correlationID string, payload EventBridgeAlive) (Envelope, error) {
	return newEvent(TypeEventBridgeAlive, target, correlationID, payload)
}

// NewEventBridgeAuthExpired builds an `event.bridge.auth_expired` envelope.
func NewEventBridgeAuthExpired(target, correlationID string, payload EventBridgeAuthExpired) (Envelope, error) {
	return newEvent(TypeEventBridgeAuthExpired, target, correlationID, payload)
}
