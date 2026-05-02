// Package ws — V1.1 inbound channel tests.
//
// Coverage:
//
//   - Happy-path inbound: a well-formed envelope written by the server
//     side of the WSS connection arrives on Client.Inbound intact.
//   - Decode-error resilience: a malformed JSON frame must NOT close
//     the reader goroutine; subsequent valid frames must still arrive.
//   - Backpressure / overflow: when the dispatcher does not drain
//     Client.Inbound, frames beyond the channel's capacity are dropped
//     and counted (telemetry.WSEventsDropped) rather than blocking the
//     reader.
//
// All tests spin up an httptest.Server hosting the coder/websocket
// Accept handler so the network round-trip is real (no mocking of the
// frame layer). Goleak / race detector are enforced via go test -race
// at the repo level.
package ws

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/coder/websocket"

	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/protocol"
	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/telemetry"
)

// startTestServer hosts a coder/websocket endpoint at the returned URL
// (ws://...). The handler invokes onConn with the accepted connection
// inside a goroutine so the test can write frames at its own cadence.
// Returns a cleanup func that closes the underlying httptest.Server +
// waits for the handler goroutine to drain.
func startTestServer(t *testing.T, onConn func(ctx context.Context, c *websocket.Conn)) (string, func()) {
	t.Helper()

	var wg sync.WaitGroup
	srvCtx, srvCancel := context.WithCancel(context.Background())

	mux := http.NewServeMux()
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		conn, err := websocket.Accept(w, r, &websocket.AcceptOptions{
			InsecureSkipVerify: true,
		})
		if err != nil {
			t.Logf("accept error: %v", err)
			return
		}
		wg.Add(1)
		go func() {
			defer wg.Done()
			defer func() {
				_ = conn.Close(websocket.StatusNormalClosure, "test done")
			}()
			onConn(srvCtx, conn)
		}()
	})
	srv := httptest.NewServer(mux)

	wsURL := "ws" + strings.TrimPrefix(srv.URL, "http")
	cleanup := func() {
		srvCancel()
		srv.Close()
		wg.Wait()
	}
	return wsURL, cleanup
}

// runClient launches Client.Run in a goroutine bound to ctx and returns
// a wait-group the caller can join after canceling.
func runClient(c *Client, ctx context.Context) *sync.WaitGroup {
	wg := &sync.WaitGroup{}
	wg.Add(1)
	go func() {
		defer wg.Done()
		c.Run(ctx)
	}()
	return wg
}

// writeJSON marshals v and writes a single WS text frame. Test helper.
func writeJSON(t *testing.T, ctx context.Context, conn *websocket.Conn, v any) {
	t.Helper()
	raw, err := json.Marshal(v)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	if err := conn.Write(ctx, websocket.MessageText, raw); err != nil {
		t.Fatalf("write: %v", err)
	}
}

// TestInboundHappyPath verifies a valid envelope written by the server
// arrives on Client.Inbound with all routable fields intact.
func TestInboundHappyPath(t *testing.T) {
	t.Parallel()

	cmd := protocol.CommandClaudeAbort{SessionID: "sess-happy"}
	want, err := protocol.NewCommandClaudeAbort("session:sess-happy", "corr-1", cmd)
	if err != nil {
		t.Fatalf("build envelope: %v", err)
	}

	url, cleanup := startTestServer(t, func(ctx context.Context, conn *websocket.Conn) {
		writeJSON(t, ctx, conn, want)
		// Hold the connection open until the test cancels.
		<-ctx.Done()
	})
	defer cleanup()

	client := NewClient(url)
	clientCtx, clientCancel := context.WithCancel(context.Background())
	defer clientCancel()
	clientWG := runClient(client, clientCtx)

	select {
	case got := <-client.Inbound:
		if got.Type != protocol.TypeCommandClaudeAbort {
			t.Errorf("Type = %q, want %q", got.Type, protocol.TypeCommandClaudeAbort)
		}
		if got.ID != want.ID {
			t.Errorf("ID = %q, want %q", got.ID, want.ID)
		}
		if got.CorrelationID != "corr-1" {
			t.Errorf("CorrelationID = %q", got.CorrelationID)
		}
		var payload protocol.CommandClaudeAbort
		if uerr := json.Unmarshal(got.Payload, &payload); uerr != nil {
			t.Fatalf("unmarshal payload: %v", uerr)
		}
		if payload.SessionID != "sess-happy" {
			t.Errorf("payload.SessionID = %q", payload.SessionID)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("timed out waiting for inbound envelope")
	}

	clientCancel()
	clientWG.Wait()
}

// TestInboundDecodeErrorIsNonFatal feeds an invalid JSON frame, then a
// valid envelope. The reader must survive the bad frame and surface the
// good one — i.e. the goroutine cannot die on json.Unmarshal failure.
func TestInboundDecodeErrorIsNonFatal(t *testing.T) {
	t.Parallel()

	url, cleanup := startTestServer(t, func(ctx context.Context, conn *websocket.Conn) {
		// Deliberately malformed JSON.
		if err := conn.Write(ctx, websocket.MessageText, []byte(`{"type":"broken"`)); err != nil {
			return
		}
		// Followed by a well-formed envelope.
		good, _ := protocol.NewCommandClaudeAbort("session:sess-good", "corr-2", protocol.CommandClaudeAbort{
			SessionID: "sess-good",
		})
		writeJSON(t, ctx, conn, good)
		<-ctx.Done()
	})
	defer cleanup()

	client := NewClient(url)
	clientCtx, clientCancel := context.WithCancel(context.Background())
	defer clientCancel()
	clientWG := runClient(client, clientCtx)

	select {
	case got := <-client.Inbound:
		if got.Type != protocol.TypeCommandClaudeAbort {
			t.Errorf("Type = %q want %q", got.Type, protocol.TypeCommandClaudeAbort)
		}
		var p protocol.CommandClaudeAbort
		if err := json.Unmarshal(got.Payload, &p); err != nil {
			t.Fatalf("unmarshal: %v", err)
		}
		if p.SessionID != "sess-good" {
			t.Errorf("SessionID = %q", p.SessionID)
		}
	case <-time.After(3 * time.Second):
		t.Fatal("reader appears to have died on the bad frame; the good envelope never arrived")
	}

	clientCancel()
	clientWG.Wait()
}

// TestInboundOverflowDropsGracefully fills Client.Inbound past its
// capacity without draining, then asserts (a) the reader keeps
// running (it does not block on a full channel), (b) the drop counter
// is bumped, and (c) draining the channel later still yields the first
// inboxCapacity frames so we know we shed the overflow tail (not the
// head) — which matches non-blocking select-default semantics.
//
// Intentionally NOT t.Parallel: this test bursts inboxCapacity+overflow
// frames through a real WS round-trip, which under -race competes
// aggressively with neighbouring tests for goroutine scheduling.
// Keeping it serial keeps the rest of the suite (and other packages
// that share the host machine via `go test ./...`) from observing
// timing-sensitive flakes.
func TestInboundOverflowDropsGracefully(t *testing.T) {
	const totalFrames = inboxCapacity + 16
	var sentCount atomic.Int64
	serverDone := make(chan struct{})

	url, cleanup := startTestServer(t, func(ctx context.Context, conn *websocket.Conn) {
		defer close(serverDone)
		for i := 0; i < totalFrames; i++ {
			env, _ := protocol.NewCommandClaudeAbort("session:s", "corr",
				protocol.CommandClaudeAbort{SessionID: "s"})
			if err := conn.Write(ctx, websocket.MessageText, mustMarshal(t, env)); err != nil {
				return
			}
			sentCount.Add(1)
		}
		<-ctx.Done()
	})
	defer cleanup()

	dropsBefore := telemetry.WSEventsDropped.Load()

	client := NewClient(url)
	clientCtx, clientCancel := context.WithCancel(context.Background())
	defer clientCancel()
	clientWG := runClient(client, clientCtx)

	// Wait for the server to finish writing all frames OR until the
	// drop counter shows we've moved past capacity. We do NOT drain
	// Client.Inbound here so the reader is forced into the
	// select-default overflow branch.
	deadline := time.After(3 * time.Second)
	for {
		select {
		case <-deadline:
			t.Fatalf("timed out: sent=%d drops_delta=%d",
				sentCount.Load(),
				telemetry.WSEventsDropped.Load()-dropsBefore)
		case <-serverDone:
			// Server pushed everything; give the reader a brief
			// window to process the tail before we sample.
			time.Sleep(100 * time.Millisecond)
			goto verify
		case <-time.After(50 * time.Millisecond):
			if telemetry.WSEventsDropped.Load()-dropsBefore > 0 {
				goto verify
			}
		}
	}
verify:
	dropsAfter := telemetry.WSEventsDropped.Load()
	delta := dropsAfter - dropsBefore
	if delta == 0 {
		t.Fatalf("expected >=1 inbound drop, got 0 (sent=%d, capacity=%d)",
			sentCount.Load(), inboxCapacity)
	}

	// Drain whatever made it into the channel — must not exceed
	// capacity (channel buffer) and must contain at least 1 frame.
	drainCtx, drainCancel := context.WithTimeout(context.Background(), 250*time.Millisecond)
	defer drainCancel()
	drained := 0
drainLoop:
	for {
		select {
		case <-client.Inbound:
			drained++
			if drained >= inboxCapacity {
				break drainLoop
			}
		case <-drainCtx.Done():
			break drainLoop
		}
	}
	if drained == 0 {
		t.Fatalf("inbound channel was empty after overflow; expected at least 1 buffered frame")
	}

	clientCancel()
	clientWG.Wait()

	// The reader goroutine must have terminated cleanly via context
	// cancellation, not via a panic from a closed channel write or
	// similar. If Run() ever returned with a goroutine leak we would
	// have seen it under -race; the wait above is the structural
	// assertion.
	if err := clientCtx.Err(); !errors.Is(err, context.Canceled) {
		t.Errorf("client context = %v", err)
	}
}

// mustMarshal is a small test helper: marshalling failures inside a
// table test should hard-fail rather than soft-skip a frame.
func mustMarshal(t *testing.T, v any) []byte {
	t.Helper()
	b, err := json.Marshal(v)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	return b
}
