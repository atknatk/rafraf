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

	logTag string

	mu   sync.Mutex
	conn *websocket.Conn
}

// NewClient constructs a Client ready to be Run.
func NewClient(url string) *Client {
	return &Client{
		URL:     url,
		Out:     make(chan protocol.Envelope, outboxCapacity),
		Inbound: make(chan protocol.Envelope, inboxCapacity),
		Done:    make(chan struct{}),
		logTag:  "[ws]",
	}
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
	defer cancelPump()

	// reader: decode every inbound frame into a protocol.Envelope and
	// fan it into c.Inbound for the dispatcher to consume. The
	// goroutine MUST NOT die on JSON decode errors — a single
	// malformed frame from a misbehaving control plane (or a future
	// envelope type this bridge hasn't been updated to know about) must
	// not knock the WSS reader offline. Only an actual conn.Read error
	// (i.e. connection close / I/O error / context cancel) propagates
	// to readerErr and triggers reconnect.
	readerErr := make(chan error, 1)
	go func() {
		for {
			_, data, err := conn.Read(pumpCtx)
			if err != nil {
				readerErr <- err
				return
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

	hb := time.NewTicker(heartbeatInterval)
	defer hb.Stop()

	for {
		select {
		case <-pumpCtx.Done():
			return ctx.Err()
		case err := <-readerErr:
			return fmt.Errorf("read: %w", err)
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
