// Package ws hosts the outbound persistent WebSocket client that ferries
// envelopes from the bridge to the control plane. T0.5.2 ports the spike
// implementation verbatim (~/Code/claude-teams-spike/bridge/main.go) into a
// dedicated package; the richer Client/Option/OnMessage surface from
// docs/11_Bridge_Spec.md §3.2 lands in later tasks.
package ws

import (
	"context"
	"encoding/json"
	"fmt"
	"math/rand"
	"os"
	"runtime"
	"sync"
	"time"

	"github.com/coder/websocket"
	"github.com/coder/websocket/wsjson"

	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/protocol"
	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/telemetry"
)

const (
	dialTimeout       = 10 * time.Second
	heartbeatInterval = 15 * time.Second
	initialBackoff    = 500 * time.Millisecond
	maxBackoff        = 30 * time.Second
	outboxCapacity    = 256
	// inboxCapacity is the buffer for inbound envelopes routed to the
	// dispatcher. Per-bridge inbound traffic is sparse (rate-limited by
	// user decisions on permission requests + an occasional
	// command.claude.abort), so 64 is comfortably above the steady-state
	// arrival rate. On overflow we drop and log: the upstream sender
	// (control plane) will time out and surface a deny — that is the
	// right failure mode (see docs/design/v1-permission-blockers.md §6
	// open question #6).
	inboxCapacity = 64

	// registerAckTimeout bounds how long connectAndPump waits for the
	// backend's agent_register_ack reply after sending agent_register.
	// On timeout the connection is torn down and the reconnect loop
	// kicks in — this matches the legacy Python agent's bias toward
	// fail-fast registration so a half-registered bridge doesn't sit
	// quietly without ever being routed traffic by the orchestrator.
	registerAckTimeout = 5 * time.Second

	// defaultLegacyHeartbeatInterval is the fallback cadence used for
	// the legacy agent_heartbeat ticker when the backend's
	// agent_register_ack omits or zeroes heartbeat_interval. It mirrors
	// the bridge's own existing ping cadence (heartbeatInterval) so the
	// extra legacy frame stays well inside the backend's 90s
	// stale-bridge window (bridge_registry_service.heartbeat_timeout).
	defaultLegacyHeartbeatInterval = 15 * time.Second

	// legacyCapabilityClaudeCode is the single capability advertised in
	// the legacy agent_register payload for V1. The backend
	// orchestrator's CapabilityRouter calls
	// bridge_registry.find_online_agent_with_capability("claude_code")
	// when iOS sends a chat message; without this entry the lookup
	// returns nil and the orchestrator falls back to a path that
	// bypasses the PreToolUse hook.
	legacyCapabilityClaudeCode = "claude_code"
)

// Client is the spike's WSClient promoted to a package-level type.
type Client struct {
	URL string
	Out chan protocol.Envelope // app → ws (outbound)
	// Inbound carries every envelope decoded from the control plane back
	// to the bridge's dispatcher loop in cmd/bridge/main.go. Capacity is
	// inboxCapacity (64); see the inboxCapacity doc comment for the
	// backpressure rationale. The reader goroutine never blocks on this
	// channel — overflows are dropped + counted in telemetry.WSEventsDropped
	// (TODO V1.4: split outbound vs inbound dropped counters) so a slow
	// consumer cannot wedge the WSS read loop.
	Inbound chan protocol.Envelope // ws → app (inbound)
	Done    chan struct{}          // signal shutdown

	// HostID is the bridge's stable identity sent in the legacy
	// agent_register payload (and echoed in every agent_heartbeat). It
	// MUST be deterministic — config.BridgeID first, then os.Hostname()
	// — so re-registers reuse the same _BridgeRecord slot in the
	// backend's bridge_registry. Defaults to os.Hostname() when blank.
	HostID string
	// Version stamps the legacy agent_register payload's "version" field
	// so the backend's AgentDetailResponse surfaces the bridge build to
	// operators. Defaults to "0.0.1-dev" matching cmd/bridge/version.go.
	Version string
	// HeartbeatInterval seeds the legacy agent_heartbeat ticker. The
	// backend's agent_register_ack may override it (server-controlled
	// cadence, see bridge_registry_service.AgentRegisterAckPayload). A
	// zero value falls through to defaultLegacyHeartbeatInterval.
	HeartbeatInterval time.Duration

	logTag string

	mu        sync.Mutex
	conn      *websocket.Conn
	startedAt time.Time
}

// NewClient constructs a Client ready to be Run. Legacy register fields
// (HostID, Version, HeartbeatInterval) default to os.Hostname() /
// "0.0.1-dev" / 15s respectively; callers (cmd/bridge/main.go) may
// override them post-construction before calling Run.
func NewClient(url string) *Client {
	return &Client{
		URL:               url,
		Out:               make(chan protocol.Envelope, outboxCapacity),
		Inbound:           make(chan protocol.Envelope, inboxCapacity),
		Done:              make(chan struct{}),
		HostID:            "",
		Version:           "0.0.1-dev",
		HeartbeatInterval: defaultLegacyHeartbeatInterval,
		logTag:            "[ws]",
		startedAt:         time.Now(),
	}
}

// resolveHostID returns the deterministic legacy host_id used in
// agent_register / agent_heartbeat. Order: configured HostID, then
// os.Hostname(), then the literal "rafraf-bridge" sentinel so the
// payload field never goes blank (the backend's AgentRegisterPayload
// rejects empty host_id with min_length=1).
func (c *Client) resolveHostID() string {
	if c.HostID != "" {
		return c.HostID
	}
	if hn, err := os.Hostname(); err == nil && hn != "" {
		return hn
	}
	return "rafraf-bridge"
}

// resolveHeartbeatInterval returns the cadence used by the legacy
// agent_heartbeat ticker. ackInterval (when > 0) wins so the backend
// stays authoritative; otherwise we fall back to the configured
// HeartbeatInterval, then the package default.
func (c *Client) resolveHeartbeatInterval(ackInterval time.Duration) time.Duration {
	if ackInterval > 0 {
		return ackInterval
	}
	if c.HeartbeatInterval > 0 {
		return c.HeartbeatInterval
	}
	return defaultLegacyHeartbeatInterval
}

// Run blocks until ctx is cancelled, reconnecting with exponential backoff
// + jitter when the underlying connection drops.
func (c *Client) Run(ctx context.Context) {
	backoff := initialBackoff
	for {
		select {
		case <-ctx.Done():
			return
		default:
		}
		if err := c.connectAndPump(ctx); err != nil {
			telemetry.WSDisconnects.Add(1)
			fmt.Fprintf(os.Stderr, "%s lost: %v; reconnecting in %s\n", c.logTag, err, backoff)
			select {
			case <-ctx.Done():
				return
			case <-time.After(backoff + jitter(backoff/2)):
			}
			backoff *= 2
			if backoff > maxBackoff {
				backoff = maxBackoff
			}
			continue
		}
		// connectAndPump returned cleanly (ctx done), exit.
		return
	}
}

// jitter returns a random duration in [0, d]. Returns 0 if d <= 0.
func jitter(d time.Duration) time.Duration {
	if d <= 0 {
		return 0
	}
	return time.Duration(rand.Int63n(int64(d) + 1))
}

func (c *Client) connectAndPump(ctx context.Context) error {
	connCtx, cancel := context.WithTimeout(ctx, dialTimeout)
	defer cancel()
	conn, _, err := websocket.Dial(connCtx, c.URL, nil)
	if err != nil {
		return fmt.Errorf("dial: %w", err)
	}
	defer func() {
		_ = conn.Close(websocket.StatusInternalError, "shutdown")
	}()

	c.mu.Lock()
	c.conn = conn
	c.mu.Unlock()
	telemetry.WSConnected.Add(1)
	telemetry.WSReconnects.Add(1)
	fmt.Fprintf(os.Stderr, "%s connected to %s\n", c.logTag, c.URL)
	defer func() {
		telemetry.WSConnected.Add(-1)
		c.mu.Lock()
		c.conn = nil
		c.mu.Unlock()
	}()

	pumpCtx, cancelPump := context.WithCancel(ctx)
	// Safety net: covers the early-return paths (e.g. agent_register
	// ack-timeout) that bail out BEFORE the heartbeat-cleanup defer is
	// registered. Calling cancel twice is idempotent.
	defer cancelPump()

	// reader: decode every inbound frame into a protocol.Envelope and
	// fan it into c.Inbound for the dispatcher to consume. The
	// goroutine MUST NOT die on JSON decode errors — a single
	// malformed frame from a misbehaving control plane (or a future
	// envelope type this bridge hasn't been updated to know about) must
	// not knock the WSS reader offline. Only an actual conn.Read error
	// (i.e. connection close / I/O error / context cancel) propagates
	// to readerErr and triggers reconnect.
	//
	// Legacy compat: agent_register_ack arrives on the same socket as
	// the new envelope protocol but is NOT a routable Envelope (no
	// correlation_id, content vs payload). The reader peeks each frame
	// for {"type":"agent_register_ack",...} BEFORE attempting envelope
	// decode and forwards the parsed ack on registerAckCh; the
	// connectAndPump goroutine consumes exactly one of those during the
	// post-dial register handshake. Subsequent acks (e.g. after a
	// re-register) are silently logged and dropped — the registry
	// already treats re-register as idempotent.
	readerErr := make(chan error, 1)
	registerAckCh := make(chan legacyRegisterAck, 1)
	go func() {
		for {
			_, data, err := conn.Read(pumpCtx)
			if err != nil {
				readerErr <- err
				return
			}
			// Cheap legacy-frame peek before envelope decode. We use a
			// minimal struct so unrelated fields (metadata, content,
			// etc.) don't bind into the same path that envelope routing
			// depends on.
			var peek legacyMessagePeek
			if perr := json.Unmarshal(data, &peek); perr == nil && isLegacyServerType(peek.Type) {
				if peek.Type == "agent_register_ack" {
					var ack legacyRegisterAck
					if uerr := json.Unmarshal(data, &ack); uerr != nil {
						fmt.Fprintf(os.Stderr, "%s legacy agent_register_ack decode error: %v\n",
							c.logTag, uerr)
						continue
					}
					select {
					case registerAckCh <- ack:
					default:
						// Already-seen ack (re-register on a still-live
						// connection — currently unreachable since we
						// register exactly once per connectAndPump but
						// keep the drop+log so future code can't wedge
						// on a full channel).
						fmt.Fprintf(os.Stderr, "%s extra agent_register_ack dropped\n", c.logTag)
					}
					continue
				}
				// Other legacy server-to-agent frames (pong from a
				// future backend, project_sync_ack, ...) are logged
				// and ignored — the V1 bridge does not consume them.
				continue
			}
			var env protocol.Envelope
			if uerr := json.Unmarshal(data, &env); uerr != nil {
				// Logged but non-fatal. The frame counter intentionally
				// stays unbumped because we never produced an envelope
				// the dispatcher could route.
				fmt.Fprintf(os.Stderr, "%s inbound decode error: %v (drop %d bytes)\n",
					c.logTag, uerr, len(data))
				continue
			}
			select {
			case c.Inbound <- env:
			default:
				// Backpressure: dispatcher has not drained the channel
				// fast enough. Drop + log + bump the same counter the
				// outbox uses (V1.4 will introduce a dedicated
				// bridge_inbound_dropped_total counter; T0.5.13 telemetry
				// surface stays untouched in V1.1).
				telemetry.WSEventsDropped.Add(1)
				fmt.Fprintf(os.Stderr, "%s inbound channel full, drop %s id=%s\n",
					c.logTag, env.Type, env.ID)
			}
		}
	}()

	// Legacy agent_register handshake (V1 backend requirement).
	// MUST happen before the main pump loop so the bridge appears in
	// bridge_registry.find_online_agent_with_capability("claude_code")
	// before any iOS chat traffic arrives.
	hostID := c.resolveHostID()
	if err := c.sendLegacyRegister(pumpCtx, conn, hostID); err != nil {
		return fmt.Errorf("agent_register send: %w", err)
	}

	ackInterval, err := c.waitForRegisterAck(pumpCtx, registerAckCh, readerErr, hostID)
	if err != nil {
		return err
	}
	hbInterval := c.resolveHeartbeatInterval(ackInterval)
	fmt.Fprintf(os.Stderr, "%s agent_registered host_id=%s heartbeat_interval=%s\n",
		c.logTag, hostID, hbInterval)

	// Legacy agent_heartbeat ticker for the lifetime of the connection.
	// Lives in its own goroutine so the main pump select stays focused
	// on the new envelope protocol (Out / Inbound / readerErr). On WS
	// write error we surface the failure via legacyHBErr so the pump
	// returns and the reconnect loop kicks in — never silently swallow.
	legacyHBErr := make(chan error, 1)
	hbDone := make(chan struct{})
	go c.runLegacyHeartbeat(pumpCtx, conn, hostID, hbInterval, legacyHBErr, hbDone)
	defer func() {
		// Cancel pumpCtx FIRST so the heartbeat goroutine's
		// `select { case <-ctx.Done(): }` fires immediately. Without this,
		// the goroutine would idle on `case <-t.C:` for up to hbInterval
		// seconds every reconnect, blocking the reconnect loop.
		cancelPump()
		// Then wait for the heartbeat goroutine to observe the cancel
		// and exit. Bounded by select in runLegacyHeartbeat — should
		// return within microseconds once pumpCtx is cancelled.
		<-hbDone
	}()

	hb := time.NewTicker(heartbeatInterval)
	defer hb.Stop()

	for {
		select {
		case <-pumpCtx.Done():
			return ctx.Err()
		case err := <-readerErr:
			return fmt.Errorf("read: %w", err)
		case err := <-legacyHBErr:
			return fmt.Errorf("legacy heartbeat: %w", err)
		case <-hb.C:
			ping := protocol.Envelope{Type: "ping", ID: protocol.NewID(), TS: protocol.NowISO()}
			if err := wsjson.Write(pumpCtx, conn, ping); err != nil {
				return fmt.Errorf("ping: %w", err)
			}
		case env := <-c.Out:
			if err := wsjson.Write(pumpCtx, conn, env); err != nil {
				return fmt.Errorf("write: %w", err)
			}
			telemetry.WSEventsForwarded.Add(1)
		}
	}
}

// ---------------------------------------------------------------------------
// Legacy agent_register / agent_heartbeat plumbing.
//
// These helpers implement the V1 backend's bridge_registry contract,
// which still keys off the pre-envelope agent_register/agent_heartbeat
// message types (apps/backend/app/api/routes/agent_ws.py
// _handle_register/_handle_heartbeat). Schemas mirror
// apps/backend/app/schemas/agent.py:AgentRegisterPayload and
// AgentHeartbeatPayload exactly — drift between this file and that
// schema will be surfaced by the integration test
// apps/backend/tests/integration/test_websocket/test_agent_ws_endpoint.py
// (which already exercises both message types end-to-end).
//
// The new envelope protocol (command.claude.* / event.session.*) is
// untouched — these are purely additive legacy frames.
// ---------------------------------------------------------------------------

// legacyMessagePeek is the minimal struct used by the reader to detect
// pre-envelope server-to-agent frames before falling through to the
// envelope decoder. We only care about the type tag.
type legacyMessagePeek struct {
	Type string `json:"type"`
}

// legacyRegisterAck mirrors AgentRegisterAckPayload from
// apps/backend/app/schemas/agent.py. The backend wraps it under
// {"type":"agent_register_ack","content":{...}}.
type legacyRegisterAck struct {
	Type    string `json:"type"`
	Content struct {
		HostID            string `json:"host_id"`
		Registered        bool   `json:"registered"`
		ServerTime        string `json:"server_time"`
		HeartbeatInterval int    `json:"heartbeat_interval"`
	} `json:"content"`
}

// isLegacyServerType returns true for any pre-envelope server-to-agent
// type tag the backend may emit. The envelope protocol uses dotted
// names ("event.session.*", "command.claude.*"), so a flat
// snake_case tag is a reliable discriminator.
func isLegacyServerType(typ string) bool {
	switch typ {
	case "agent_register_ack",
		"project_sync_ack",
		"pong":
		return true
	}
	return false
}

// legacyRegisterMessage mirrors RegisterMessage from
// apps/_archive/agent-python-v0.1/agent/core/protocol.py. Field names
// follow the snake_case Pydantic convention used by the backend.
type legacyRegisterMessage struct {
	Type    string                `json:"type"`
	Content legacyRegisterContent `json:"content"`
}

type legacyRegisterContent struct {
	HostID       string   `json:"host_id"`
	Capabilities []string `json:"capabilities"`
	OSInfo       string   `json:"os_info"`
	Version      string   `json:"version"`
}

// legacyHeartbeatMessage mirrors HeartbeatMessage from the legacy
// Python agent. Resources is a flat struct because the backend's
// AgentHeartbeatPayload requires the four fields verbatim (the
// _handle_heartbeat handler in agent_ws.py builds a ResourceInfo
// directly from them via float(...)).
type legacyHeartbeatMessage struct {
	Type    string                 `json:"type"`
	Content legacyHeartbeatContent `json:"content"`
}

type legacyHeartbeatContent struct {
	HostID        string                 `json:"host_id"`
	Status        string                 `json:"status"`
	UptimeSeconds int64                  `json:"uptime_seconds"`
	ActiveTasks   int                    `json:"active_tasks"`
	Resources     legacyHeartbeatResrc   `json:"resources"`
	ClaudeProcess []legacyClaudeProcInfo `json:"claude_processes"`
}

type legacyHeartbeatResrc struct {
	CPUUsagePercent    float64 `json:"cpu_usage_percent"`
	MemoryUsagePercent float64 `json:"memory_usage_percent"`
	DiskUsagePercent   float64 `json:"disk_usage_percent"`
	DiskFreeGB         float64 `json:"disk_free_gb"`
}

type legacyClaudeProcInfo struct {
	PID        int     `json:"pid"`
	CPUPercent float64 `json:"cpu_percent"`
	MemoryMB   float64 `json:"memory_mb"`
	StartedAt  string  `json:"started_at,omitempty"`
	Cmdline    string  `json:"cmdline,omitempty"`
}

// sendLegacyRegister marshals + writes a single agent_register frame.
// Capabilities is hard-pinned to ["claude_code"] for V1; widening this
// is a downstream change that must coordinate with the backend's
// AgentCapability enum + orchestrator routing.
func (c *Client) sendLegacyRegister(ctx context.Context, conn *websocket.Conn, hostID string) error {
	msg := legacyRegisterMessage{
		Type: "agent_register",
		Content: legacyRegisterContent{
			HostID:       hostID,
			Capabilities: []string{legacyCapabilityClaudeCode},
			OSInfo:       runtime.GOOS + "/" + runtime.GOARCH,
			Version:      c.Version,
		},
	}
	return wsjson.Write(ctx, conn, msg)
}

// waitForRegisterAck blocks for at most registerAckTimeout for an
// agent_register_ack to land on ackCh. Returns the ack-supplied
// heartbeat interval (converted from seconds) or 0 when the field is
// absent. A timeout / read-loop error / rejection is returned as an
// error so the caller can fail-fast and let the reconnect loop kick in.
func (c *Client) waitForRegisterAck(ctx context.Context, ackCh <-chan legacyRegisterAck, readerErr <-chan error, hostID string) (time.Duration, error) {
	select {
	case ack := <-ackCh:
		if !ack.Content.Registered {
			fmt.Fprintf(os.Stderr, "%s agent_register_failed host_id=%s ack.registered=false\n",
				c.logTag, hostID)
			return 0, fmt.Errorf("agent_register rejected by backend (host_id=%s)", hostID)
		}
		if ack.Content.HostID != "" && ack.Content.HostID != hostID {
			// Backend echoed a different host_id — log loudly but
			// honor the original since the registry indexes off the
			// payload we sent.
			fmt.Fprintf(os.Stderr, "%s agent_register_ack host_id mismatch sent=%s got=%s\n",
				c.logTag, hostID, ack.Content.HostID)
		}
		return time.Duration(ack.Content.HeartbeatInterval) * time.Second, nil
	case err := <-readerErr:
		// Surface the read error to the caller so the same failure
		// drives both the registration failure and the reconnect.
		fmt.Fprintf(os.Stderr, "%s agent_register_failed host_id=%s read_err=%v\n",
			c.logTag, hostID, err)
		return 0, fmt.Errorf("agent_register await: %w", err)
	case <-time.After(registerAckTimeout):
		fmt.Fprintf(os.Stderr, "%s agent_register_failed host_id=%s reason=ack_timeout\n",
			c.logTag, hostID)
		return 0, fmt.Errorf("agent_register: ack timeout after %s", registerAckTimeout)
	case <-ctx.Done():
		return 0, ctx.Err()
	}
}

// runLegacyHeartbeat owns the periodic agent_heartbeat goroutine. Exits
// on (a) ctx cancel via a clean nil signal on hbDone, or (b) WS write
// error via a single non-blocking send into errCh — the pump select
// picks the latter up and returns to trigger reconnect. The goroutine
// always closes hbDone exactly once.
func (c *Client) runLegacyHeartbeat(ctx context.Context, conn *websocket.Conn, hostID string, interval time.Duration, errCh chan<- error, hbDone chan<- struct{}) {
	defer close(hbDone)

	t := time.NewTicker(interval)
	defer t.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-t.C:
			msg := c.buildLegacyHeartbeat(hostID)
			if err := wsjson.Write(ctx, conn, msg); err != nil {
				// Non-blocking send: errCh has cap=1 and the pump is
				// the sole consumer. If the pump has already returned
				// (e.g. readerErr fired first) we drop silently — the
				// connection is going down regardless.
				select {
				case errCh <- err:
				default:
				}
				return
			}
		}
	}
}

// buildLegacyHeartbeat returns an agent_heartbeat payload with the
// minimum fields the backend's _handle_heartbeat requires. V1 does not
// surface real CPU/memory/disk metrics from the bridge (the host has
// no psutil equivalent in-process), so we send a status-only payload
// with zeroed resources. The backend treats zero values as valid (the
// AgentHeartbeatPayload uses ge=0 bounds, not gt=0) and the registry
// only flips to OFFLINE on missed-heartbeat-timeout, not on resource
// thresholds.
func (c *Client) buildLegacyHeartbeat(hostID string) legacyHeartbeatMessage {
	uptime := int64(time.Since(c.startedAt).Seconds())
	if uptime < 0 {
		uptime = 0
	}
	return legacyHeartbeatMessage{
		Type: "agent_heartbeat",
		Content: legacyHeartbeatContent{
			HostID:        hostID,
			Status:        "online",
			UptimeSeconds: uptime,
			ActiveTasks:   0,
			Resources: legacyHeartbeatResrc{
				CPUUsagePercent:    0,
				MemoryUsagePercent: 0,
				DiskUsagePercent:   0,
				DiskFreeGB:         0,
			},
			ClaudeProcess: []legacyClaudeProcInfo{},
		},
	}
}

// Send enqueues env for delivery. If the outbox is full the envelope is
// dropped (matching spike behavior) and telemetry.WSEventsDropped is bumped.
//
// Send has the signature required by claude.EnvelopeSender so it can be
// passed directly as a sink callback.
func (c *Client) Send(env protocol.Envelope) {
	select {
	case c.Out <- env:
	default:
		telemetry.WSEventsDropped.Add(1)
		fmt.Fprintf(os.Stderr, "%s outbox full, drop %s\n", c.logTag, env.Type)
	}
}
