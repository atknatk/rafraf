// Command rafraf-perm-hook is the PreToolUse hook binary that the
// claude CLI invokes via the per-session settings overlay generated
// by the bridge runner. It is the producer side of the V1.2
// PreToolUse approval flow described in
// docs/design/v1-permission-blockers.md §2.1.2.
//
// PROTOCOL
//
//   - stdin  → JSON envelope from claude CLI (PreToolUse hook
//     contract). Required fields:
//     hook_event_name: "PreToolUse"
//     tool_name:       string
//     tool_input:      object (verbatim claude payload)
//     session_id:      string (claude session UUID)
//     tool_use_id:     string (opaque PreToolUse ID)
//
//   - $RAFRAF_BRIDGE_PERM_SOCK → Unix-domain socket path the bridge
//     created at startup. The hook dials it once.
//
//   - bridge ← {tool_use_id, tool_name, tool_input, session_id}
//     (one JSON object). Hook then blocks on a read for the reply.
//
//   - bridge → {decision: "allow"|"block", reason?}
//     (one JSON object). Hook prints this verbatim to stdout, exits 0.
//
// # FAIL-SAFE
//
// Every error path resolves to a deny print on stdout. The exit
// code is 0 in EVERY case — claude CLI relies on the JSON, not the
// process exit, for the hook decision (and a non-zero exit is
// interpreted as a hook crash, not a deny). Specifically:
//
//   - $RAFRAF_BRIDGE_PERM_SOCK unset → deny (bridge isn't running).
//   - Dial fails (timeout, refused) → deny.
//   - stdin malformed → deny.
//   - bridge reply malformed / EOF → deny.
//   - any panic recovered → deny.
//
// We log to stderr at every error site so the bridge logger can
// scoop up hook-internal failures (claude tees hook stderr into its
// own stream-json output as system/hook_response frames).
//
// # V1.2 LIMITATION
//
// updated_input is not yet implemented. The CommandClaudePermissionDecision
// schema reserves the field for V2 MCP-style edits but the hook
// returns the original {decision: "allow"} which leaves the tool_input
// untouched. Backend MUST NOT send updated_input until the hook is
// extended.
package main

import (
	"encoding/json"
	"fmt"
	"io"
	"net"
	"os"
	"strconv"
	"time"
)

const (
	// dialTimeout caps the UDS connect attempt. Bridge is a
	// localhost UDS so 5s is generous; failure here means the
	// bridge isn't running OR the socket path is stale.
	dialTimeout = 5 * time.Second

	// defaultReadTimeout caps the wait on the bridge's reply when
	// the bridge does NOT inject RAFRAF_BRIDGE_PERM_TIMEOUT_MS
	// (older bridge build OR test scenarios). Bumped from 60s →
	// 190s in V1.4-followup so the hook never EOFs before the
	// broker's own per-request ceiling fires.
	//
	// 190s = broker's defaultRequestTimeout (180s,
	// permission.defaultRequestTimeout) + 10s grace for the
	// decision-relay round trip (broker timer fire → JSON marshal
	// → UDS write). The matching upper bound on the broker's
	// permission_timeout config is 600s (config.MaxPermissionTimeout);
	// when ops dial the broker above 190s the
	// RAFRAF_BRIDGE_PERM_TIMEOUT_MS env var below carries the
	// effective ceiling so this default never bottlenecks the
	// runtime path.
	defaultReadTimeout = 190 * time.Second

	// sockEnvVar is the env var the bridge runner injects before
	// spawning claude. Unset → bridge isn't supervising us → fail safe.
	sockEnvVar = "RAFRAF_BRIDGE_PERM_SOCK"

	// timeoutEnvVar is the optional env var the bridge runner
	// injects (alongside sockEnvVar) so the hook's read deadline
	// tracks the broker's effective permission_timeout config in
	// lockstep. Value is the broker's per-request ceiling expressed
	// as milliseconds (e.g. "180000"); the hook adds timeoutGrace
	// on top before applying it as a deadline. Unset / unparseable
	// / non-positive → defaultReadTimeout.
	//
	// Wiring: cfg.PermissionTimeout (apps/rafraf-bridge/internal/config)
	// → runner.buildEnv → here. A single TOML knob therefore controls
	// the broker timer, the hook deadline, and the claude CLI's
	// PreToolUse hook timeout (also plumbed via the settings
	// overlay) in lockstep.
	timeoutEnvVar = "RAFRAF_BRIDGE_PERM_TIMEOUT_MS"

	// timeoutGrace is the slack added on top of the env-var-supplied
	// broker timeout when computing the hook's read deadline. Same
	// 10s rationale as defaultReadTimeout: covers the broker's
	// own decision-relay latency without spuriously denying.
	timeoutGrace = 10 * time.Second
)

// claudeStdin is the shape claude CLI writes to a PreToolUse hook's
// stdin. Field names per the claude CLI hooks documentation.
type claudeStdin struct {
	HookEventName string          `json:"hook_event_name"`
	ToolName      string          `json:"tool_name"`
	ToolInput     json.RawMessage `json:"tool_input"`
	SessionID     string          `json:"session_id"`
	ToolUseID     string          `json:"tool_use_id"`
}

// brokerRequest is the wire frame the hook writes to the broker UDS.
// Mirrors permission.hookRequest in the broker package.
type brokerRequest struct {
	ToolUseID string          `json:"tool_use_id"`
	ToolName  string          `json:"tool_name"`
	ToolInput json.RawMessage `json:"tool_input"`
	SessionID string          `json:"session_id"`
}

// brokerReply is the wire frame the broker writes back. Mirrors
// permission.hookReply.
type brokerReply struct {
	Decision string `json:"decision"`
	Reason   string `json:"reason,omitempty"`
}

// hookOutput is exactly what claude CLI expects to read from the
// hook's stdout. {decision: "allow"} lets the tool call proceed;
// {decision: "block", reason: "..."} cancels it and the reason is
// surfaced to the model + the user.
type hookOutput struct {
	Decision string `json:"decision"`
	Reason   string `json:"reason,omitempty"`
}

func main() {
	// Run the actual hook in a separate function so we can use
	// defer + recover + a single exit-code path. The hook ALWAYS
	// exits 0; the JSON on stdout is the decision channel.
	defer func() {
		if r := recover(); r != nil {
			_, _ = fmt.Fprintf(os.Stderr, "rafraf-perm-hook: panic recovered: %v\n", r)
			emitDeny("hook panic")
		}
	}()
	run(os.Stdin, os.Stdout, os.Stderr, os.Getenv(sockEnvVar), resolveReadTimeout(os.Getenv(timeoutEnvVar)))
	os.Exit(0)
}

// resolveReadTimeout returns the hook's UDS read deadline. The raw
// argument is the value of RAFRAF_BRIDGE_PERM_TIMEOUT_MS expressed
// as milliseconds (string-encoded so env-var plumbing is trivial).
// Empty / unparseable / non-positive falls back to defaultReadTimeout.
// A positive value adds timeoutGrace on top so the hook always
// outlives the broker's own per-request ceiling by the same 10s
// slack the static default carries.
//
// Exported as a free function for direct unit testing — every branch
// is covered in main_test.go::TestResolveReadTimeout.
func resolveReadTimeout(raw string) time.Duration {
	if raw == "" {
		return defaultReadTimeout
	}
	ms, err := strconv.Atoi(raw)
	if err != nil || ms <= 0 {
		return defaultReadTimeout
	}
	return time.Duration(ms)*time.Millisecond + timeoutGrace
}

// run is the testable entrypoint — accepts injected I/O, the
// socket path, AND the resolved read deadline so unit tests can
// exercise every branch without touching real environment variables.
//
// The deadline argument is consumed verbatim (no extra grace added
// here) — resolveReadTimeout is responsible for computing the
// effective value, including applying timeoutGrace on top of any
// broker-supplied ceiling.
func run(stdin io.Reader, stdout, stderr io.Writer, sock string, readDeadline time.Duration) {
	if sock == "" {
		_, _ = fmt.Fprintln(stderr, "rafraf-perm-hook: $RAFRAF_BRIDGE_PERM_SOCK unset; denying")
		writeOutput(stdout, hookOutput{Decision: "block", Reason: "bridge unavailable"})
		return
	}

	body, err := io.ReadAll(stdin)
	if err != nil {
		_, _ = fmt.Fprintf(stderr, "rafraf-perm-hook: read stdin: %v\n", err)
		writeOutput(stdout, hookOutput{Decision: "block", Reason: "stdin read failed"})
		return
	}
	var inbound claudeStdin
	if err := json.Unmarshal(body, &inbound); err != nil {
		_, _ = fmt.Fprintf(stderr, "rafraf-perm-hook: parse stdin: %v\n", err)
		writeOutput(stdout, hookOutput{Decision: "block", Reason: "malformed hook payload"})
		return
	}
	// V1.2-fix L5: settings overlay only registers PreToolUse, but if the
	// operator (or future claude version) reuses this binary for a
	// different event class we must not silently block tool _output_.
	// Bail with deny only on PreToolUse; otherwise the hook is a no-op.
	if inbound.HookEventName != "" && inbound.HookEventName != "PreToolUse" {
		_, _ = fmt.Fprintf(stderr, "rafraf-perm-hook: unexpected hook_event_name %q; deferring to claude\n", inbound.HookEventName)
		writeOutput(stdout, hookOutput{Decision: "allow", Reason: "non-PreToolUse event passthrough"})
		return
	}

	conn, err := net.DialTimeout("unix", sock, dialTimeout)
	if err != nil {
		_, _ = fmt.Fprintf(stderr, "rafraf-perm-hook: dial %s: %v\n", sock, err)
		writeOutput(stdout, hookOutput{Decision: "block", Reason: "bridge dial failed"})
		return
	}
	defer func() { _ = conn.Close() }()

	// Belt-and-braces: a zero/negative deadline arg from a future
	// caller would translate to time.Now() (immediate timeout) on
	// SetDeadline, which would deny every request. Fall back to the
	// static default so the hook stays useful even if the wiring
	// regresses.
	effectiveDeadline := readDeadline
	if effectiveDeadline <= 0 {
		effectiveDeadline = defaultReadTimeout
	}
	if err := conn.SetDeadline(time.Now().Add(effectiveDeadline)); err != nil {
		// Non-fatal — proceed but the read may stall on a wedged
		// broker. We accept the risk because the broker has its
		// own per-request timer.
		_, _ = fmt.Fprintf(stderr, "rafraf-perm-hook: set deadline: %v\n", err)
	}

	req := brokerRequest{
		ToolUseID: inbound.ToolUseID,
		ToolName:  inbound.ToolName,
		ToolInput: inbound.ToolInput,
		SessionID: inbound.SessionID,
	}
	reqBody, err := json.Marshal(req)
	if err != nil {
		_, _ = fmt.Fprintf(stderr, "rafraf-perm-hook: marshal request: %v\n", err)
		writeOutput(stdout, hookOutput{Decision: "block", Reason: "internal marshal error"})
		return
	}
	reqBody = append(reqBody, '\n')
	if _, err := conn.Write(reqBody); err != nil {
		_, _ = fmt.Fprintf(stderr, "rafraf-perm-hook: write request: %v\n", err)
		writeOutput(stdout, hookOutput{Decision: "block", Reason: "bridge write failed"})
		return
	}

	var reply brokerReply
	if err := json.NewDecoder(conn).Decode(&reply); err != nil {
		_, _ = fmt.Fprintf(stderr, "rafraf-perm-hook: decode reply: %v\n", err)
		writeOutput(stdout, hookOutput{Decision: "block", Reason: "bridge reply failed"})
		return
	}

	// Pass through verbatim — broker decided.
	out := hookOutput(reply)
	if out.Decision != "allow" && out.Decision != "block" {
		// Defensive: if broker emits anything else, fail safe.
		_, _ = fmt.Fprintf(stderr, "rafraf-perm-hook: unknown decision %q; denying\n", out.Decision)
		writeOutput(stdout, hookOutput{Decision: "block", Reason: "broker invalid decision"})
		return
	}
	writeOutput(stdout, out)
}

// emitDeny is the panic-path helper that prints a deny and never
// raises further errors. Stdout is the only channel claude inspects.
func emitDeny(reason string) {
	_ = json.NewEncoder(os.Stdout).Encode(hookOutput{Decision: "block", Reason: reason})
}

// writeOutput marshals + writes one JSON line to stdout. Trailing
// newline keeps line-oriented consumers happy. Errors here are
// fatal-but-silent; without stdout we can't communicate at all.
func writeOutput(w io.Writer, out hookOutput) {
	_ = json.NewEncoder(w).Encode(out)
}
