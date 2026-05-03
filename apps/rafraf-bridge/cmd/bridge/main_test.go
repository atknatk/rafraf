// V1.3 wiring tests — exercise dispatchCommand's permission handlers
// and the broker → wsEventSink closure plumbed in claude.Runner.Run.
//
// Tests A/D/E hit dispatchCommand directly (no goroutines, no WS). Test
// B drives the broker handler closure through the same code path the
// runner installs (the closure literal appears in both places; the test
// pins the contract that "broker fires handler → handler invokes
// sink.OnPermissionRequest"). Test C bursts 100 deny envelopes through
// dispatchCommand to assert the synchronous handlers stay non-blocking
// under load (V1.1 reviewer M1 contract).
//
// We use a real permission.Broker (with a short UDS path under /tmp so
// macOS SUN_PATH=104 stays satisfied) instead of a mock so the contract
// is enforced end-to-end and can't drift if the broker grows internal
// state in V2+.
package main

import (
	"context"
	"encoding/json"
	"io"
	"log/slog"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/claude"
	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/permission"
	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/protocol"
	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/ws"
)

// shortSockPath mirrors the helper in internal/permission/broker_test.go
// — macOS caps unix socket paths at 104 bytes (SUN_PATH) so we mint a
// short directory under /tmp. Keeping the helper local to the test file
// (rather than promoting it to the permission package) avoids leaking a
// test-only API into production code.
func shortSockPath(t *testing.T, name string) string {
	t.Helper()
	dir, err := os.MkdirTemp("/tmp", "v13")
	if err != nil {
		t.Fatalf("mkdtemp: %v", err)
	}
	t.Cleanup(func() { _ = os.RemoveAll(dir) })
	return filepath.Join(dir, name)
}

// silentLogger discards every log record. Tests assert behaviour on the
// broker / channels directly, not on log output.
func silentLogger() *slog.Logger {
	return slog.New(slog.NewTextHandler(io.Discard, nil))
}

// newTestBroker spins up a real permission.Broker on a short UDS path
// + a t.Cleanup-bound shutdown so each test gets an isolated instance.
func newTestBroker(t *testing.T) *permission.Broker {
	t.Helper()
	sock := shortSockPath(t, "b.sock")
	b, err := permission.NewBroker(sock, silentLogger())
	if err != nil {
		t.Fatalf("NewBroker: %v", err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	if err := b.Start(ctx); err != nil {
		cancel()
		_ = b.Close()
		t.Fatalf("Broker.Start: %v", err)
	}
	t.Cleanup(func() {
		cancel()
		_ = b.Close()
	})
	return b
}

// newDispatchHarness assembles the minimum dispatchCommand needs: a
// runner (kept idle so abort/run paths stay no-ops in these tests), a
// fresh ws.Client (we never call Run on it; the Inbound/Out channels
// are accessed directly when needed), a broker, and a logger.
func newDispatchHarness(t *testing.T) (*claude.Runner, *ws.Client, *permission.Broker, *slog.Logger) {
	t.Helper()
	logger := silentLogger()
	// ws.NewClient just allocates channels + state — it does not dial.
	client := ws.NewClient("ws://127.0.0.1:0/test")
	runner := claude.NewRunner(nil, logger)
	broker := newTestBroker(t)
	return runner, client, broker, logger
}

// buildDecisionEnvelope constructs a command.claude.permission.{allow,deny}
// envelope shaped exactly like one the backend would emit so the
// dispatchCommand tests exercise the same json.Unmarshal path that runs
// in production.
func buildDecisionEnvelope(t *testing.T, typ string, requestID string) protocol.Envelope {
	t.Helper()
	payload := protocol.CommandClaudePermissionDecision{
		SessionID: "sess-test",
		RequestID: requestID,
		Decision:  "allow",
	}
	if typ == protocol.TypeCommandClaudePermissionDeny {
		payload.Decision = "deny"
	}
	body, err := json.Marshal(payload)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	return protocol.Envelope{
		Type:          typ,
		ID:            protocol.NewID(),
		TS:            protocol.NowISO(),
		CorrelationID: "rpc-test",
		Payload:       body,
	}
}

// ----- Test A — wiring: dispatchCommand permission.allow → broker.Resolve.

// TestDispatchCommand_PermissionAllow_ResolvesBroker asserts that an
// inbound command.claude.permission.allow envelope reaches the broker's
// Resolve method and wakes a waiter that was registered through the
// broker's normal RequestDecision path. The waiter goroutine plays the
// role of the in-flight PreToolUse hook subprocess.
func TestDispatchCommand_PermissionAllow_ResolvesBroker(t *testing.T) {
	t.Parallel()
	runner, client, broker, logger := newDispatchHarness(t)

	// Fixed RequestID so the two sides agree.
	const reqID = "req-allow-1"
	ev := protocol.EventSessionPermissionRequest{
		SessionID: "sess-test",
		RequestID: reqID,
		ToolName:  "Bash",
		Risk:      "high",
		TimeoutMs: 2000,
	}

	// SetRequestHandler must be installed BEFORE RequestDecision is
	// called — the broker auto-denies when handler == nil. The handler
	// here is intentionally a no-op: we drive Resolve via dispatchCommand
	// below instead of from the handler closure (this is what the V1.3
	// runner closure would do via the WS sink).
	broker.SetRequestHandler(func(_ protocol.EventSessionPermissionRequest) {})

	decisionCh := make(chan permission.Decision, 1)
	go func() {
		// The actual hook subprocess would block on a UDS read here;
		// using RequestDecision directly is the documented public path
		// for tests that bypass the UDS layer (see the broker doc
		// block under "RequestDecision").
		decisionCh <- broker.RequestDecision(context.Background(), ev)
	}()

	// Tiny wait so the goroutine above has a chance to register the
	// waiter map entry before dispatch fires Resolve. The broker
	// guarantees Resolve-after-RequestDecision will hit the waiter, but
	// Resolve-before-RequestDecision is the documented "drop silently"
	// branch — we want to exercise the success path here.
	waitForPending(t, broker, reqID, time.Second)

	env := buildDecisionEnvelope(t, protocol.TypeCommandClaudePermissionAllow, reqID)
	dispatchCommand(context.Background(), runner, client, logger, broker, nil, env)

	select {
	case d := <-decisionCh:
		if d != permission.DecisionAllow {
			t.Fatalf("decision = %q, want allow", d)
		}
	case <-time.After(time.Second):
		t.Fatalf("waiter did not wake within 1s after dispatchCommand")
	}
}

// TestDispatchCommand_PermissionDeny_ResolvesBroker mirrors the allow
// case but for the deny RPC.
func TestDispatchCommand_PermissionDeny_ResolvesBroker(t *testing.T) {
	t.Parallel()
	runner, client, broker, logger := newDispatchHarness(t)

	const reqID = "req-deny-1"
	ev := protocol.EventSessionPermissionRequest{
		SessionID: "sess-test",
		RequestID: reqID,
		ToolName:  "Write",
		Risk:      "medium",
		TimeoutMs: 2000,
	}
	broker.SetRequestHandler(func(_ protocol.EventSessionPermissionRequest) {})

	decisionCh := make(chan permission.Decision, 1)
	go func() {
		decisionCh <- broker.RequestDecision(context.Background(), ev)
	}()
	waitForPending(t, broker, reqID, time.Second)

	env := buildDecisionEnvelope(t, protocol.TypeCommandClaudePermissionDeny, reqID)
	dispatchCommand(context.Background(), runner, client, logger, broker, nil, env)

	select {
	case d := <-decisionCh:
		if d != permission.DecisionDeny {
			t.Fatalf("decision = %q, want deny", d)
		}
	case <-time.After(time.Second):
		t.Fatalf("waiter did not wake within 1s after dispatchCommand")
	}
}

// ----- Test B — handler closure: broker → wsEventSink.OnPermissionRequest.

// TestWsEventSink_OnPermissionRequest_FlowsThroughBroker installs a
// SetRequestHandler closure shaped exactly like the one
// claude.Runner.Run wires up (see runner.go), drives a RequestDecision
// through the broker, and asserts the synthesised envelope lands in
// ws.Client.Out with the originating correlation_id intact.
//
// This pins the per-run correlation_id discipline: even though the
// broker is process-wide, every envelope it emits during a particular
// run carries the run's rpc id so the backend dispatcher can route it
// back into the right per-RPC subscriber queue.
func TestWsEventSink_OnPermissionRequest_FlowsThroughBroker(t *testing.T) {
	t.Parallel()
	_, client, broker, logger := newDispatchHarness(t)

	const correlationID = "rpc-handler-test"
	sink := &wsEventSink{ws: client, correlationID: correlationID}

	// Closure is the same one claude.Runner.Run installs; we copy the
	// shape rather than calling Runner.Run because spinning a real
	// claude subprocess is out of scope for this test.
	broker.SetRequestHandler(func(ev protocol.EventSessionPermissionRequest) {
		if err := sink.OnPermissionRequest(ev); err != nil {
			logger.Warn("permission_request egress failed", "err", err)
		}
	})

	ev := protocol.EventSessionPermissionRequest{
		SessionID: "sess-handler",
		RequestID: "req-handler",
		ToolName:  "Edit",
		Risk:      "medium",
		TimeoutMs: 1000,
	}

	// Drive RequestDecision in a goroutine because the handler runs in
	// its own goroutine (see broker.go RequestDecision: `go handler(ev)`)
	// — the call blocks until the per-request timeout otherwise.
	go broker.RequestDecision(context.Background(), ev)

	// Wait for the envelope to land in ws.Client.Out. Polling beats a
	// fixed sleep because handler dispatch is `go handler(ev)` and
	// Out's buffered capacity is large enough that we never block.
	envelope := waitForOutbound(t, client, time.Second)

	if envelope.Type != protocol.TypeEventSessionPermissionRequest {
		t.Fatalf("envelope type = %q, want %q", envelope.Type, protocol.TypeEventSessionPermissionRequest)
	}
	if envelope.CorrelationID != correlationID {
		t.Fatalf("correlation_id = %q, want %q", envelope.CorrelationID, correlationID)
	}
	if envelope.Target != "session:sess-handler" {
		t.Fatalf("target = %q, want session:sess-handler", envelope.Target)
	}
	var got protocol.EventSessionPermissionRequest
	if err := json.Unmarshal(envelope.Payload, &got); err != nil {
		t.Fatalf("payload unmarshal: %v", err)
	}
	if got.RequestID != "req-handler" {
		t.Fatalf("payload RequestID = %q, want req-handler", got.RequestID)
	}
	if got.ToolName != "Edit" {
		t.Fatalf("payload ToolName = %q, want Edit", got.ToolName)
	}
}

// ----- Test C — non-blocking dispatch under burst load.

// TestDispatchCommand_PermissionDenyBurst_NonBlocking fires 100
// back-to-back deny envelopes through dispatchCommand and asserts the
// total elapsed time stays well under 50 ms. This pins the V1.1
// reviewer M1 contract: synchronous work in dispatchCommand must never
// block the bounded ws.Client.Inbound channel. broker.Resolve's
// non-blocking send + drop-on-full guarantees this even when no waiter
// is registered (the case here).
func TestDispatchCommand_PermissionDenyBurst_NonBlocking(t *testing.T) {
	t.Parallel()
	runner, client, broker, logger := newDispatchHarness(t)

	const burst = 100
	envelopes := make([]protocol.Envelope, burst)
	for i := 0; i < burst; i++ {
		// Distinct request_ids so Resolve doesn't dedup; nothing is
		// registered for any of them so each call falls through the
		// "unknown request" debug branch — still must be non-blocking.
		envelopes[i] = buildDecisionEnvelope(t, protocol.TypeCommandClaudePermissionDeny, "req-burst-"+itoa(i))
	}

	start := time.Now()
	for _, env := range envelopes {
		dispatchCommand(context.Background(), runner, client, logger, broker, nil, env)
	}
	elapsed := time.Since(start)

	if elapsed > 50*time.Millisecond {
		t.Fatalf("100x dispatchCommand took %v, want < 50ms (non-blocking contract)", elapsed)
	}
}

// ----- Test D — malformed payload: missing request_id.

// TestDispatchCommand_PermissionAllow_MissingRequestID_NoPanic asserts
// that an envelope with an empty request_id is handled with a warn log
// (no broker call, no panic). The broker.Resolve("", ...) call would
// otherwise hit the "unknown request" debug branch silently, masking
// the contract violation; the early return + warn log surfaces the
// upstream bug instead.
func TestDispatchCommand_PermissionAllow_MissingRequestID_NoPanic(t *testing.T) {
	t.Parallel()
	runner, client, broker, logger := newDispatchHarness(t)

	// Register a sentinel waiter for empty-string request_id so we can
	// detect any accidental Resolve("") call. If dispatchCommand were
	// to forward the malformed envelope, this channel would receive a
	// decision and the test would fail.
	sentinel := make(chan permission.Decision, 1)
	broker.SetRequestHandler(func(_ protocol.EventSessionPermissionRequest) {})
	go func() {
		ev := protocol.EventSessionPermissionRequest{RequestID: "", TimeoutMs: 200}
		sentinel <- broker.RequestDecision(context.Background(), ev)
	}()

	env := buildDecisionEnvelope(t, protocol.TypeCommandClaudePermissionAllow, "")
	// Must not panic.
	dispatchCommand(context.Background(), runner, client, logger, broker, nil, env)

	// The sentinel waiter should time out (DecisionExpired), proving
	// that dispatchCommand did NOT forward the malformed allow.
	select {
	case d := <-sentinel:
		if d != permission.DecisionExpired {
			t.Fatalf("sentinel woke with decision %q — dispatchCommand must not forward empty request_id", d)
		}
	case <-time.After(500 * time.Millisecond):
		t.Fatalf("sentinel did not time out within 500ms — broker is wedged?")
	}
}

// TestDispatchCommand_PermissionAllow_MalformedJSON_NoPanic asserts
// that a non-JSON payload is rejected via warn log, not panic. Same
// shape as Test D but mutates the envelope payload to invalid JSON.
func TestDispatchCommand_PermissionAllow_MalformedJSON_NoPanic(t *testing.T) {
	t.Parallel()
	runner, client, broker, logger := newDispatchHarness(t)

	env := protocol.Envelope{
		Type:    protocol.TypeCommandClaudePermissionAllow,
		ID:      protocol.NewID(),
		TS:      protocol.NowISO(),
		Payload: json.RawMessage(`{"this is": not json}`),
	}
	dispatchCommand(context.Background(), runner, client, logger, broker, nil, env)
	// No assertion needed — we just need this to return without panic.
	// A panic would surface as a test runtime failure.
}

// ----- Test E — nil broker on permission case must not panic.

// TestDispatchCommand_PermissionAllow_NilBroker_NoPanic exercises the
// degraded V1.2 path where broker startup failed. dispatchCommand must
// short-circuit with a warn log instead of dereferencing nil. Both
// allow and deny variants are checked because they have independent
// nil guards.
func TestDispatchCommand_PermissionAllow_NilBroker_NoPanic(t *testing.T) {
	t.Parallel()
	logger := silentLogger()
	client := ws.NewClient("ws://127.0.0.1:0/test")
	runner := claude.NewRunner(nil, logger)

	allowEnv := buildDecisionEnvelope(t, protocol.TypeCommandClaudePermissionAllow, "req-nil-allow")
	denyEnv := buildDecisionEnvelope(t, protocol.TypeCommandClaudePermissionDeny, "req-nil-deny")

	// Both must return without panicking. The compiled-in nil guard is
	// the load-bearing assertion.
	dispatchCommand(context.Background(), runner, client, logger, nil, nil, allowEnv)
	dispatchCommand(context.Background(), runner, client, logger, nil, nil, denyEnv)
}

// ---------------------------------------------------------------------------
// Helpers.
// ---------------------------------------------------------------------------

// waitForOutbound polls ws.Client.Out for up to timeout, returning the
// first envelope or failing the test if none arrives. The handler that
// emits the envelope runs in its own goroutine (broker dispatches with
// `go handler(ev)`), so a polling helper is more robust than a fixed
// sleep.
func waitForOutbound(t *testing.T, c *ws.Client, timeout time.Duration) protocol.Envelope {
	t.Helper()
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		select {
		case env := <-c.Out:
			return env
		case <-time.After(10 * time.Millisecond):
		}
	}
	t.Fatalf("no outbound envelope within %v", timeout)
	return protocol.Envelope{}
}

// waitForPending busy-waits (lightly) for a request_id to appear in the
// broker's pending map. Implemented by attempting a Resolve with a
// sentinel decision and observing whether a fresh waiter would survive
// — but that would mutate state. Instead, we expose nothing about the
// broker internals and just wait a small fixed duration; the broker's
// RequestDecision path registers the entry before invoking the handler,
// and the handler in tests A/B is a no-op so the registration is
// effectively synchronous from the goroutine's perspective. A short
// sleep is sufficient here and matches the broker_test.go pattern.
func waitForPending(t *testing.T, _ *permission.Broker, _ string, _ time.Duration) {
	t.Helper()
	// Yield the scheduler a few times so the RequestDecision goroutine
	// has a chance to register the waiter. The pending map is keyed +
	// guarded by mu inside the broker; this is the minimum-knowledge
	// way to await registration without adding a test-only hook.
	for i := 0; i < 5; i++ {
		time.Sleep(2 * time.Millisecond)
	}
}

// itoa is a tiny inline integer-to-string for the burst test loop —
// strconv.Itoa would work too but using a local helper keeps the
// import list focused on the wire types.
func itoa(i int) string {
	if i == 0 {
		return "0"
	}
	var b strings.Builder
	negative := i < 0
	if negative {
		i = -i
	}
	digits := make([]byte, 0, 4)
	for i > 0 {
		digits = append(digits, byte('0'+i%10))
		i /= 10
	}
	if negative {
		b.WriteByte('-')
	}
	for j := len(digits) - 1; j >= 0; j-- {
		b.WriteByte(digits[j])
	}
	return b.String()
}
