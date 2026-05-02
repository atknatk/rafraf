// Package permission owns the bridge-side V1.2 PreToolUse approval flow
// described in docs/design/v1-permission-blockers.md §2.1.2 and §2.2.1.
//
// The Broker is a per-bridge-process singleton that:
//
//  1. Listens on a Unix-domain socket (default
//     "$TMPDIR/rafraf-bridge-perm-<pid>.sock", mode 0600). The path is
//     namespaced per-PID so concurrent bridge processes never collide
//     and gets exposed via Sock() so the runner can inject it into the
//     claude subprocess env (RAFRAF_BRIDGE_PERM_SOCK).
//
//  2. Accepts one connection per PreToolUse hook subprocess. Each hook
//     sends a single JSON request frame describing the pending tool
//     call, then blocks on read for the broker's reply.
//
//  3. Calls the V1.3-supplied request handler (set via
//     SetRequestHandler) which forwards the corresponding
//     event.session.permission_request envelope through the WS sink.
//
//  4. Blocks the per-connection goroutine on a Decision channel
//     registered in the in-flight map[requestID]. The matching call to
//     Resolve() unblocks it.
//
//  5. On timeout (TimeoutMs from the envelope, default 30 000) writes
//     a deny reply and removes the waiter so a late Resolve is a noop.
//
// CRITICAL CONTRACTS
//
//   - Resolve MUST be non-blocking. The V1.3 inbound dispatcher loop
//     (cmd/bridge/main.go::runInboundDispatcher) is a single consumer
//     of the bounded ws.Client.Inbound channel; a blocking handler
//     would back the whole channel up. We use a non-blocking send into
//     a buffered (cap 1) channel and drop silently if the waiter is
//     already gone (timed out / closed).
//
//   - Risk classification is bridge-authoritative. The backend just
//     consumes the "low"|"medium"|"high" string. See risk.go.
//
//   - Hook fail-safe: any error path between hook stdin and broker
//     reply MUST resolve to a deny. The hook binary
//     (internal/cmd/rafraf-perm-hook) enforces this on the producer
//     side; the broker enforces it here on the consumer side.
//
// # V1.2 SCOPE
//
// V1.2 ships the broker + UDS listener + hook binary + risk classifier
// + runner --settings overlay. SetRequestHandler is left nil at
// startup; until V1.3 wires it, the broker logs a warning on each
// inbound request and resolves with deny+"handler not installed". V1.3
// will install the closure that builds the
// EventSessionPermissionRequest envelope and pushes it into the WS
// sink, plus add the dispatchCommand cases for
// command.claude.permission.allow|deny that route into Resolve().
package permission

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io/fs"
	"log/slog"
	"net"
	"os"
	"path/filepath"
	"strconv"
	"sync"
	"sync/atomic"
	"time"

	"github.com/google/uuid"

	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/protocol"
)

// Decision is the canonical broker outcome surfaced to the hook reply.
type Decision string

const (
	// DecisionAllow lets the tool call proceed.
	DecisionAllow Decision = "allow"
	// DecisionDeny blocks the tool call (user-driven).
	DecisionDeny Decision = "deny"
	// DecisionExpired is returned when no Resolve call arrived within
	// the per-request timeout. Treated identically to deny on the wire
	// (the hook prints {"decision":"block","reason":"timeout"}); kept
	// distinct in-process so callers/audit can distinguish the two.
	DecisionExpired Decision = "expired"
)

// hookRequest is the JSON frame the rafraf-perm-hook binary sends as
// the first (and only) read on each UDS connection. tool_use_id is the
// claude PreToolUse-supplied opaque ID; we echo it on the reply so the
// hook can sanity-check (defence in depth — pairing is by connection,
// not by ID, but having both lets us spot impersonation).
type hookRequest struct {
	ToolUseID string          `json:"tool_use_id"`
	ToolName  string          `json:"tool_name"`
	ToolInput json.RawMessage `json:"tool_input"`
	SessionID string          `json:"session_id"`
}

// hookReply is the JSON frame the broker writes back on each UDS
// connection. The shape matches the claude CLI's documented hook
// contract: {decision: "allow"|"block", reason?}. We use "block" for
// deny so claude treats the result as a refusal directly.
type hookReply struct {
	Decision string `json:"decision"`
	Reason   string `json:"reason,omitempty"`
}

// defaultRequestTimeout is the broker's per-request ceiling when the
// hook envelope omits TimeoutMs (or the V1.3 wiring leaves it zero) AND
// no explicit timeout was supplied to the broker constructor.
//
// Bumped from 30s → 180s in V1.4-followup after the live test on
// 2026-05-02 surfaced a race: real-world claude cold-start (~5–10s) +
// network RTT (~2s) + iOS sheet display + user deliberation routinely
// exceeded 30s, causing the broker to deny on its own timer ~3s
// before the user's "Allow once" tap reached the backend. The new
// 180s value matches the backend's per-category default
// (apps/backend/app/services/approval_service.py — see the
// `_evaluate_request_timeout_seconds` helper / record.timeout_seconds
// defaults of 180–300s) so the iOS countdown driven by the envelope's
// timeout_ms field also auto-extends end-to-end.
//
// Operators can override via the `permission_timeout` TOML key on the
// bridge config; the override is bounded to (0, 590s] in
// apps/rafraf-bridge/internal/config/config.go::Validate (capped at
// claude CLI's 600s hook-execution limit minus the 10s grace the
// runner stamps onto the overlay).
//
// End-to-end lockstep — a single `permission_timeout` knob propagates
// to all three downstream layers in one shot:
//   - rafraf-perm-hook UDS read deadline ← RAFRAF_BRIDGE_PERM_TIMEOUT_MS
//     env var (broker timeout + 10s grace; default 190s).
//   - claude CLI PreToolUse hook `timeout` overlay field ←
//     Runner.claudeHookTimeout() (broker timeout + 10s grace; default
//     190s, written into the per-session --settings JSON).
//   - Backend ApprovalService awaiter ← bridge_timeout_seconds in the
//     event.session.permission_request envelope (driven by
//     effectiveTimeout(); backend already clamps the iOS countdown
//     against this).
const defaultRequestTimeout = 180 * time.Second

// brokerCWD is captured once at New() so risk classification can
// compare paths against it without re-stat'ing on every request.
// Stored on the Broker (not as a package-level var) to keep tests
// hermetic.

// Broker owns the UDS listener and in-flight permission requests.
//
// Lifecycle:
//
//   - New(...) creates the listener + initialises internal state.
//   - SetRequestHandler(fn) installs the V1.3 callback. Optional;
//     leaving it nil yields a "handler not installed" deny on every
//     request and is the V1.2 default.
//   - Start(ctx) spawns the Accept loop. Returns immediately. Caller
//     MUST defer Close() so the listener is removed and in-flight
//     waiters are unblocked.
//   - Close() may be called multiple times safely.
type Broker struct {
	sock     string
	listener net.Listener
	logger   *slog.Logger
	cwd      string

	// timeout is the per-request ceiling applied when the inbound
	// envelope's TimeoutMs is zero. Initialised from the constructor
	// argument; values <= 0 fall back to defaultRequestTimeout at
	// request time.
	timeout time.Duration

	// onRequest is the V1.3-supplied callback that converts a
	// hook-side request into an EventSessionPermissionRequest envelope
	// and pushes it through the WS sink. May be nil in V1.2.
	onRequestMu sync.RWMutex
	onRequest   func(ev protocol.EventSessionPermissionRequest)

	mu      sync.Mutex
	pending map[string]chan Decision

	closed atomic.Bool
	done   chan struct{}
}

// NewBroker creates the listener at sockPath. When sockPath is empty
// the broker derives "$TMPDIR/rafraf-bridge-perm-<pid>.sock". The file
// is created with mode 0600 so only the bridge owner can connect.
//
// If the path is already taken AND the holder is not a live PID the
// broker reclaims it (best-effort os.Remove + retry). When the holder
// IS a live PID NewBroker returns an error so a duplicate bridge
// startup fails loudly rather than silently stealing requests.
//
// The per-request timeout defaults to defaultRequestTimeout (180s).
// Callers that need a different ceiling — typically the bridge daemon
// reading the operator's `permission_timeout` TOML override — should
// use NewBrokerWithTimeout instead.
func NewBroker(sockPath string, logger *slog.Logger) (*Broker, error) {
	return NewBrokerWithTimeout(sockPath, 0, logger)
}

// NewBrokerWithTimeout is the explicit constructor that lets the
// daemon main wire an operator-configured per-request ceiling
// (config.PermissionTimeout) into the broker. A timeout <= 0 falls
// through to defaultRequestTimeout, so the bridge keeps booting in a
// safe mode even if config validation is bypassed.
//
// The validation contract for the operator-supplied value lives in
// internal/config/config.go::Validate (currently bounded to
// (0, 600s]); the broker accepts anything here so unit tests can
// exercise short timeouts (e.g. 100ms) without rerouting through the
// config layer.
func NewBrokerWithTimeout(sockPath string, timeout time.Duration, logger *slog.Logger) (*Broker, error) {
	if logger == nil {
		logger = slog.Default()
	}
	if sockPath == "" {
		sockPath = defaultSockPath()
	}
	cwd, err := os.Getwd()
	if err != nil {
		// Non-fatal — risk classifier will fall back to "" cwd which
		// just means write-outside-cwd is the default branch.
		logger.Warn("permission broker: getwd failed", "err", err)
		cwd = ""
	}
	if err := ensureSockDir(sockPath); err != nil {
		return nil, fmt.Errorf("permission: ensure sock dir: %w", err)
	}
	if err := reclaimSock(sockPath); err != nil {
		return nil, fmt.Errorf("permission: reclaim sock: %w", err)
	}
	ln, err := net.Listen("unix", sockPath)
	if err != nil {
		return nil, fmt.Errorf("permission: listen %q: %w", sockPath, err)
	}
	if err := os.Chmod(sockPath, 0o600); err != nil {
		// Best-effort — on some FUSE/sandboxed filesystems chmod is a
		// no-op. We still want the listener up because the path lives
		// inside $TMPDIR which is owner-only by default.
		logger.Warn("permission broker: chmod sock failed", "err", err, "sock", sockPath)
	}
	b := &Broker{
		sock:     sockPath,
		listener: ln,
		logger:   logger,
		cwd:      cwd,
		timeout:  timeout,
		pending:  make(map[string]chan Decision),
		done:     make(chan struct{}),
	}
	logger.Info("permission broker listening",
		"sock", sockPath,
		"cwd", cwd,
		"timeout", b.effectiveTimeout().String(),
	)
	return b, nil
}

// effectiveTimeout returns the broker's per-request ceiling, falling
// back to defaultRequestTimeout when the constructor was given a
// non-positive value. Centralised so the log line at startup and the
// outbound envelope's TimeoutMs derivation cannot drift.
func (b *Broker) effectiveTimeout() time.Duration {
	if b.timeout > 0 {
		return b.timeout
	}
	return defaultRequestTimeout
}

// Sock returns the active socket path.
func (b *Broker) Sock() string {
	return b.sock
}

// SetRequestHandler installs the V1.3-supplied callback that converts
// a hook request into an outbound permission_request envelope.
// Setting it after Start() is safe — the broker reads the handler
// under a read lock at request-time.
func (b *Broker) SetRequestHandler(fn func(ev protocol.EventSessionPermissionRequest)) {
	b.onRequestMu.Lock()
	b.onRequest = fn
	b.onRequestMu.Unlock()
}

// Start spawns the Accept loop. Returns immediately. The loop runs
// until ctx is done OR Close() is called. Idempotent — calling Start
// twice yields the second call as a noop.
func (b *Broker) Start(ctx context.Context) error {
	if b.closed.Load() {
		return errors.New("permission: broker is closed")
	}
	go b.acceptLoop(ctx)
	go func() {
		<-ctx.Done()
		_ = b.Close()
	}()
	b.onRequestMu.RLock()
	handler := b.onRequest
	b.onRequestMu.RUnlock()
	if handler == nil {
		b.logger.Warn("permission broker: request handler not installed; all requests will deny",
			"sock", b.sock,
		)
	}
	return nil
}

// acceptLoop is the per-connection fan-out. Each accept spawns a
// goroutine that reads one request, calls RequestDecision, writes the
// reply, closes. Bounded by ctx + per-request timeout — no leaks even
// if the hook subprocess hangs.
func (b *Broker) acceptLoop(ctx context.Context) {
	for {
		conn, err := b.listener.Accept()
		if err != nil {
			if b.closed.Load() {
				return
			}
			// Transient network errors shouldn't kill the loop;
			// permanent ones (listener closed) will be observed as
			// closed.Load() == true on the next iteration.
			if errors.Is(err, net.ErrClosed) {
				return
			}
			b.logger.Warn("permission broker: accept error", "err", err)
			continue
		}
		go b.handleConn(ctx, conn)
	}
}

// handleConn services one hook subprocess.
func (b *Broker) handleConn(ctx context.Context, conn net.Conn) {
	defer func() {
		_ = conn.Close()
	}()
	// Bound the read so a misbehaving hook can't pin a goroutine
	// forever. The hook protocol is a single-shot request/response so
	// 10s of read-deadline headroom is plenty.
	if err := conn.SetReadDeadline(time.Now().Add(10 * time.Second)); err != nil {
		b.logger.Debug("permission broker: set read deadline", "err", err)
	}
	var req hookRequest
	dec := json.NewDecoder(conn)
	if err := dec.Decode(&req); err != nil {
		b.logger.Warn("permission broker: bad hook request", "err", err)
		_ = writeReply(conn, hookReply{Decision: "block", Reason: "malformed request"})
		return
	}
	// Reset deadline now that we have the request — the wait for the
	// user's decision is governed by the per-request timeout below.
	if err := conn.SetReadDeadline(time.Time{}); err != nil {
		b.logger.Debug("permission broker: clear read deadline", "err", err)
	}

	// Build the outbound envelope payload. RequestID is a fresh UUID
	// owned by the broker so the V1.3 round-trip can target this
	// specific waiter via Resolve.
	requestID := uuid.NewString()
	risk, reason := classifyRisk(req.ToolName, req.ToolInput, b.cwd)
	preview := inputPreview(req.ToolInput)
	envPayload := protocol.EventSessionPermissionRequest{
		SessionID:    req.SessionID,
		RequestID:    requestID,
		ToolName:     req.ToolName,
		ToolInput:    req.ToolInput,
		InputPreview: preview,
		Risk:         risk,
		Reason:       reason,
		// effectiveTimeout honours the operator-supplied
		// PermissionTimeout config (or defaultRequestTimeout when
		// unset). Plumbed into the envelope so the iOS countdown +
		// backend ApprovalService timeout track this exact value.
		TimeoutMs: int(b.effectiveTimeout() / time.Millisecond),
	}

	decision := b.RequestDecision(ctx, envPayload)
	var reply hookReply
	switch decision {
	case DecisionAllow:
		reply = hookReply{Decision: "allow"}
	case DecisionDeny:
		reply = hookReply{Decision: "block", Reason: "user denied"}
	case DecisionExpired:
		reply = hookReply{Decision: "block", Reason: "timeout"}
	default:
		// Unknown decision — fail safe to deny.
		reply = hookReply{Decision: "block", Reason: "internal error"}
	}
	if err := writeReply(conn, reply); err != nil {
		b.logger.Warn("permission broker: write reply failed",
			"err", err,
			"request_id", requestID,
			"decision", string(decision),
		)
	}
}

// RequestDecision registers a waiter, fires the V1.3 callback (or
// auto-denies when none is installed), and blocks until Resolve is
// called OR the per-request timeout fires OR ctx is cancelled.
//
// The caller is the per-connection goroutine in acceptLoop; this
// method is exported so future direct callers (e.g. integration tests
// that bypass the UDS layer) can drive the broker the same way.
func (b *Broker) RequestDecision(ctx context.Context, ev protocol.EventSessionPermissionRequest) Decision {
	timeout := time.Duration(ev.TimeoutMs) * time.Millisecond
	if timeout <= 0 {
		// envelope didn't carry an explicit ceiling — fall back to
		// the broker's effective timeout (operator-configured or
		// defaultRequestTimeout).
		timeout = b.effectiveTimeout()
	}

	ch := make(chan Decision, 1)
	b.mu.Lock()
	if b.closed.Load() {
		b.mu.Unlock()
		return DecisionExpired
	}
	b.pending[ev.RequestID] = ch
	b.mu.Unlock()

	defer func() {
		b.mu.Lock()
		// Compare-and-delete: another Resolve might have raced in
		// between timeout fire and this defer; either way removing
		// our channel is safe.
		if cur, ok := b.pending[ev.RequestID]; ok && cur == ch {
			delete(b.pending, ev.RequestID)
		}
		b.mu.Unlock()
	}()

	b.onRequestMu.RLock()
	handler := b.onRequest
	b.onRequestMu.RUnlock()
	if handler == nil {
		b.logger.Warn("permission broker: deny — no request handler installed",
			"request_id", ev.RequestID,
			"tool_name", ev.ToolName,
			"risk", ev.Risk,
		)
		return DecisionDeny
	}
	// Fire-and-forget — the handler is expected to push the envelope
	// onto the WS sink. If it blocks (it shouldn't) the broker still
	// times out via the timer below, which is the correct fail-safe.
	go handler(ev)

	timer := time.NewTimer(timeout)
	defer timer.Stop()

	select {
	case decision := <-ch:
		return decision
	case <-timer.C:
		b.logger.Warn("permission broker: request expired",
			"request_id", ev.RequestID,
			"tool_name", ev.ToolName,
			"timeout", timeout.String(),
		)
		return DecisionExpired
	case <-ctx.Done():
		b.logger.Info("permission broker: request cancelled",
			"request_id", ev.RequestID,
			"err", ctx.Err(),
		)
		return DecisionExpired
	case <-b.done:
		b.logger.Info("permission broker: request cancelled by close",
			"request_id", ev.RequestID,
		)
		return DecisionExpired
	}
}

// Resolve unblocks the matching RequestDecision call. NON-BLOCKING by
// contract (V1.1 reviewer M1) — performs a non-blocking send into the
// pending channel; if the channel was already drained (timeout) or
// never registered (unknown ID, late dispatch) the call is dropped
// silently with a debug log.
func (b *Broker) Resolve(requestID string, decision Decision) {
	b.mu.Lock()
	ch, ok := b.pending[requestID]
	b.mu.Unlock()
	if !ok {
		b.logger.Debug("permission broker: resolve for unknown request",
			"request_id", requestID,
			"decision", string(decision),
		)
		return
	}
	select {
	case ch <- decision:
	default:
		// Already resolved by an earlier branch (timeout, close,
		// duplicate dispatch). Safe to drop.
		b.logger.Debug("permission broker: resolve dropped (already resolved)",
			"request_id", requestID,
			"decision", string(decision),
		)
	}
}

// Close shuts down the listener and unblocks every in-flight waiter
// with DecisionExpired. Safe to call multiple times. Returns the
// listener's Close error on first call, nil on subsequent calls.
func (b *Broker) Close() error {
	if !b.closed.CompareAndSwap(false, true) {
		return nil
	}
	close(b.done)
	err := b.listener.Close()
	// Drain any pending waiters by closing their channels. They will
	// observe the broker's done channel and return DecisionExpired.
	b.mu.Lock()
	for id, ch := range b.pending {
		select {
		case ch <- DecisionExpired:
		default:
		}
		delete(b.pending, id)
	}
	b.mu.Unlock()
	// Best-effort socket cleanup — the listener removed it on close
	// in most cases but not all (e.g. SO_REUSE paths). Idempotent.
	if rmErr := os.Remove(b.sock); rmErr != nil && !errors.Is(rmErr, fs.ErrNotExist) {
		b.logger.Debug("permission broker: sock cleanup", "err", rmErr, "sock", b.sock)
	}
	return err
}

// writeReply marshals + writes a hook reply with a short write
// deadline so a stalled hook subprocess can't wedge the goroutine.
func writeReply(conn net.Conn, reply hookReply) error {
	if err := conn.SetWriteDeadline(time.Now().Add(5 * time.Second)); err != nil {
		// Non-fatal — the write below either succeeds or we surface
		// the error there.
		_ = err
	}
	body, err := json.Marshal(reply)
	if err != nil {
		return fmt.Errorf("permission: marshal reply: %w", err)
	}
	body = append(body, '\n')
	if _, err := conn.Write(body); err != nil {
		return fmt.Errorf("permission: write reply: %w", err)
	}
	return nil
}

// defaultSockPath returns the per-PID socket path under $TMPDIR (or
// /tmp on systems where $TMPDIR is unset).
func defaultSockPath() string {
	dir := os.TempDir()
	name := "rafraf-bridge-perm-" + strconv.Itoa(os.Getpid()) + ".sock"
	return filepath.Join(dir, name)
}

// ensureSockDir creates the parent directory for sockPath if missing.
// $TMPDIR always exists in practice but custom paths used in tests
// might not.
func ensureSockDir(sockPath string) error {
	dir := filepath.Dir(sockPath)
	if dir == "" {
		return nil
	}
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return fmt.Errorf("mkdir %q: %w", dir, err)
	}
	return nil
}

// reclaimSock attempts to remove a stale socket file at sockPath if it
// exists. Returns nil when the path is free OR was successfully
// reclaimed; returns an error only when the path exists, removal
// fails, AND the file is plausibly an active listener (checked by a
// fast Dial probe).
func reclaimSock(sockPath string) error {
	info, err := os.Stat(sockPath)
	if err != nil {
		if errors.Is(err, fs.ErrNotExist) {
			return nil
		}
		return err
	}
	// Only reclaim socket files — refuse to clobber regular files.
	if info.Mode()&fs.ModeSocket == 0 {
		return fmt.Errorf("path %q exists and is not a socket (mode %s)", sockPath, info.Mode())
	}
	// Probe with a quick connect; if it succeeds, another bridge is
	// alive and we should fail loudly instead of stealing the path.
	conn, dialErr := net.DialTimeout("unix", sockPath, 200*time.Millisecond)
	if dialErr == nil {
		_ = conn.Close()
		return fmt.Errorf("socket %q is in use by another process", sockPath)
	}
	if err := os.Remove(sockPath); err != nil {
		return fmt.Errorf("remove stale socket %q: %w", sockPath, err)
	}
	return nil
}

// SweepStaleArtifacts removes leftover bridge sockets and per-session
// settings overlays from a previous run. Best-effort — logs warnings
// but never returns an error so a failed sweep does not gate startup.
//
// The sweep targets:
//   - $TMPDIR/rafraf-bridge-perm-*.sock (other than ours), unbound to
//     a live process. The reclaim probe is a fast Dial — connecting
//     successfully means it's in use and we leave it alone.
//   - $TMPDIR/rafraf-bridge-settings-*.json older than maxAge.
//
// `selfSock` may be empty; when non-empty we never delete that path
// (the live broker's own socket).
func SweepStaleArtifacts(logger *slog.Logger, selfSock string, maxAge time.Duration) {
	if logger == nil {
		logger = slog.Default()
	}
	if maxAge <= 0 {
		maxAge = time.Hour
	}
	dir := os.TempDir()
	entries, err := os.ReadDir(dir)
	if err != nil {
		logger.Debug("permission sweep: readdir", "err", err, "dir", dir)
		return
	}
	now := time.Now()
	for _, ent := range entries {
		name := ent.Name()
		full := filepath.Join(dir, name)
		switch {
		case isBridgeSock(name):
			if full == selfSock {
				continue
			}
			// If we can dial it, leave it alone.
			if c, derr := net.DialTimeout("unix", full, 100*time.Millisecond); derr == nil {
				_ = c.Close()
				continue
			}
			if rerr := os.Remove(full); rerr != nil && !errors.Is(rerr, fs.ErrNotExist) {
				logger.Debug("permission sweep: stale sock remove failed", "err", rerr, "path", full)
			}
		case isBridgeSettings(name):
			info, ierr := ent.Info()
			if ierr != nil {
				continue
			}
			if now.Sub(info.ModTime()) < maxAge {
				continue
			}
			if rerr := os.Remove(full); rerr != nil && !errors.Is(rerr, fs.ErrNotExist) {
				logger.Debug("permission sweep: stale settings remove failed", "err", rerr, "path", full)
			}
		}
	}
}

func isBridgeSock(name string) bool {
	const prefix = "rafraf-bridge-perm-"
	const suffix = ".sock"
	return len(name) > len(prefix)+len(suffix) &&
		name[:len(prefix)] == prefix &&
		name[len(name)-len(suffix):] == suffix
}

func isBridgeSettings(name string) bool {
	const prefix = "rafraf-bridge-settings-"
	const suffix = ".json"
	return len(name) > len(prefix)+len(suffix) &&
		name[:len(prefix)] == prefix &&
		name[len(name)-len(suffix):] == suffix
}
