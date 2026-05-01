// Package ws hosts the outbound persistent WebSocket client that ferries
// envelopes from the bridge to the control plane. T0.5.2 ports the spike
// implementation verbatim (~/Code/claude-teams-spike/bridge/main.go) into a
// dedicated package; the richer Client/Option/OnMessage surface from
// docs/11_Bridge_Spec.md §3.2 lands in later tasks.
package ws

import (
	"context"
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
)

// Client is the spike's WSClient promoted to a package-level type.
type Client struct {
	URL  string
	Out  chan protocol.Envelope // app → ws
	Done chan struct{}          // signal shutdown

	logTag string

	mu   sync.Mutex
	conn *websocket.Conn
}

// NewClient constructs a Client ready to be Run.
func NewClient(url string) *Client {
	return &Client{
		URL:    url,
		Out:    make(chan protocol.Envelope, outboxCapacity),
		Done:   make(chan struct{}),
		logTag: "[ws]",
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

	// reader: drain incoming frames; spike does not act on them.
	readerErr := make(chan error, 1)
	go func() {
		for {
			_, _, err := conn.Read(pumpCtx)
			if err != nil {
				readerErr <- err
				return
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
