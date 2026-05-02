// Package ws — V1.x legacy agent_register / agent_heartbeat tests.
//
// Coverage:
//
//   - TestLegacyRegisterSentOnConnect: bridge sends agent_register with
//     correct host_id + capabilities + os_info + version immediately
//     after WS upgrade.
//   - TestLegacyRegisterAckHonorsHeartbeatInterval: the heartbeat ticker
//     uses the cadence supplied by the backend's agent_register_ack.
//   - TestLegacyHeartbeatLoop: bridge emits agent_heartbeat at the
//     configured cadence with the expected schema fields.
//   - TestLegacyRegisterAckTimeoutTriggersReconnect: missing
//     agent_register_ack tears down the connection and the reconnect
//     loop kicks in (counter advances).
//
// All tests rely on the shared startTestServer helper in client_test.go.
// We share the same package (no _test suffix) so the helper + the
// internal type names (legacyRegisterMessage, legacyHeartbeatMessage,
// registerAckTimeout) are accessible.
package ws

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"runtime"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/coder/websocket"

	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/telemetry"
)

// readLegacyMessage reads one frame from conn and unmarshals it into a
// generic map so the test can assert on the type tag without binding
// to a single payload struct. Returns (nil, false) on read error
// (typically context cancel during cleanup) so callers running inside
// onConn goroutines can exit gracefully without invoking t.Fatalf
// from a non-test goroutine.
func readLegacyMessage(t *testing.T, ctx context.Context, conn *websocket.Conn) (map[string]any, bool) {
	t.Helper()
	_, data, err := conn.Read(ctx)
	if err != nil {
		return nil, false
	}
	var m map[string]any
	if uerr := json.Unmarshal(data, &m); uerr != nil {
		t.Logf("decode frame %q: %v", string(data), uerr)
		return nil, false
	}
	return m, true
}

// writeLegacyAckSafe wraps writeLegacyAck so the goroutine variant
// does not fatal-exit during shutdown. It returns true on success.
func writeLegacyAckSafe(ctx context.Context, conn *websocket.Conn, hostID string, hbSeconds int) bool {
	ack := map[string]any{
		"type": "agent_register_ack",
		"content": map[string]any{
			"host_id":            hostID,
			"registered":         true,
			"server_time":        time.Now().UTC().Format(time.RFC3339),
			"heartbeat_interval": hbSeconds,
		},
	}
	raw, err := json.Marshal(ack)
	if err != nil {
		return false
	}
	return conn.Write(ctx, websocket.MessageText, raw) == nil
}

// extractContent descends into m["content"] and asserts it is a map.
// Centralising the assertion keeps the per-test boilerplate small.
func extractContent(t *testing.T, m map[string]any) map[string]any {
	t.Helper()
	c, ok := m["content"].(map[string]any)
	if !ok {
		t.Fatalf("expected map content, got %T (%v)", m["content"], m["content"])
	}
	return c
}

// TestLegacyRegisterSentOnConnect asserts the bridge fires an
// agent_register frame immediately after WS upgrade with the V1
// schema: host_id, capabilities=["claude_code"], os_info, version.
func TestLegacyRegisterSentOnConnect(t *testing.T) {
	t.Parallel()

	registered := make(chan map[string]any, 1)

	url, cleanup := startTestServer(t, func(ctx context.Context, conn *websocket.Conn) {
		// First frame should be agent_register.
		msg, ok := readLegacyMessage(t, ctx, conn)
		if !ok {
			return
		}
		select {
		case registered <- msg:
		default:
		}
		// Send ack so the bridge does not loop on register-timeout.
		writeLegacyAckSafe(ctx, conn, "test-host", 60)
		<-ctx.Done()
	})
	defer cleanup()

	client := NewClient(url)
	client.HostID = "test-host"
	client.Version = "test-1.2.3"
	client.HeartbeatInterval = 5 * time.Second

	clientCtx, clientCancel := context.WithCancel(context.Background())
	defer clientCancel()
	clientWG := runClient(client, clientCtx)

	select {
	case msg := <-registered:
		if msg["type"] != "agent_register" {
			t.Fatalf("first frame type = %v, want agent_register", msg["type"])
		}
		content := extractContent(t, msg)
		if content["host_id"] != "test-host" {
			t.Errorf("host_id = %v, want test-host", content["host_id"])
		}
		caps, ok := content["capabilities"].([]any)
		if !ok {
			t.Fatalf("capabilities type = %T", content["capabilities"])
		}
		if len(caps) != 1 || caps[0] != legacyCapabilityClaudeCode {
			t.Errorf("capabilities = %v, want [%q]", caps, legacyCapabilityClaudeCode)
		}
		if !strings.Contains(content["os_info"].(string), runtime.GOOS) {
			t.Errorf("os_info = %v, want containing %q", content["os_info"], runtime.GOOS)
		}
		if content["version"] != "test-1.2.3" {
			t.Errorf("version = %v, want test-1.2.3", content["version"])
		}
	case <-time.After(2 * time.Second):
		t.Fatal("timed out waiting for agent_register frame")
	}

	clientCancel()
	clientWG.Wait()
}

// TestLegacyRegisterAckHonorsHeartbeatInterval verifies the bridge
// switches its heartbeat cadence to the value supplied by the backend
// in agent_register_ack (overriding the configured fallback).
func TestLegacyRegisterAckHonorsHeartbeatInterval(t *testing.T) {
	t.Parallel()

	// Server sends ack with heartbeat_interval=1 (second). We then
	// time the gap between the first two heartbeats — should be ~1s,
	// not the configured 30s fallback.
	heartbeatTimes := make(chan time.Time, 4)

	url, cleanup := startTestServer(t, func(ctx context.Context, conn *websocket.Conn) {
		// Drain the agent_register frame.
		if _, ok := readLegacyMessage(t, ctx, conn); !ok {
			return
		}
		if !writeLegacyAckSafe(ctx, conn, "hb-host", 1) {
			return
		}
		// Then capture heartbeat arrivals.
		for {
			msg, ok := readLegacyMessage(t, ctx, conn)
			if !ok {
				return
			}
			if msg["type"] == "agent_heartbeat" {
				select {
				case heartbeatTimes <- time.Now():
				default:
				}
			}
		}
	})
	defer cleanup()

	client := NewClient(url)
	client.HostID = "hb-host"
	client.Version = "test"
	// Configured fallback would be 30s — should be overridden by ack.
	client.HeartbeatInterval = 30 * time.Second

	clientCtx, clientCancel := context.WithCancel(context.Background())
	defer clientCancel()
	clientWG := runClient(client, clientCtx)

	// Wait for two heartbeats. Allow generous slack for CI.
	var first, second time.Time
	timeout := time.After(5 * time.Second)
	for i := 0; i < 2; i++ {
		select {
		case ts := <-heartbeatTimes:
			if i == 0 {
				first = ts
			} else {
				second = ts
			}
		case <-timeout:
			t.Fatalf("timed out waiting for heartbeat #%d", i+1)
		}
	}

	gap := second.Sub(first)
	// 1s ack interval — gap should be ~1s, NOT ~30s. Allow [0.5s, 3s].
	if gap < 500*time.Millisecond || gap > 3*time.Second {
		t.Errorf("heartbeat gap = %s, expected ~1s (ack honored)", gap)
	}

	clientCancel()
	clientWG.Wait()
}

// TestLegacyHeartbeatLoop verifies the bridge sends agent_heartbeat
// frames at the configured cadence with the expected schema.
func TestLegacyHeartbeatLoop(t *testing.T) {
	t.Parallel()

	heartbeats := make(chan map[string]any, 4)

	url, cleanup := startTestServer(t, func(ctx context.Context, conn *websocket.Conn) {
		if _, ok := readLegacyMessage(t, ctx, conn); !ok { // agent_register
			return
		}
		// Use a 1s heartbeat interval so the test runs quickly.
		if !writeLegacyAckSafe(ctx, conn, "loop-host", 1) {
			return
		}
		for {
			msg, ok := readLegacyMessage(t, ctx, conn)
			if !ok {
				return
			}
			if msg["type"] == "agent_heartbeat" {
				select {
				case heartbeats <- msg:
				default:
				}
			}
		}
	})
	defer cleanup()

	client := NewClient(url)
	client.HostID = "loop-host"
	client.Version = "v9"

	clientCtx, clientCancel := context.WithCancel(context.Background())
	defer clientCancel()
	clientWG := runClient(client, clientCtx)

	select {
	case hb := <-heartbeats:
		if hb["type"] != "agent_heartbeat" {
			t.Fatalf("type = %v", hb["type"])
		}
		content := extractContent(t, hb)
		if content["host_id"] != "loop-host" {
			t.Errorf("host_id = %v", content["host_id"])
		}
		if content["status"] != "online" {
			t.Errorf("status = %v, want online", content["status"])
		}
		if _, ok := content["uptime_seconds"]; !ok {
			t.Error("uptime_seconds missing")
		}
		if _, ok := content["active_tasks"]; !ok {
			t.Error("active_tasks missing")
		}
		resources, ok := content["resources"].(map[string]any)
		if !ok {
			t.Fatalf("resources type = %T", content["resources"])
		}
		for _, key := range []string{"cpu_usage_percent", "memory_usage_percent", "disk_usage_percent", "disk_free_gb"} {
			if _, ok := resources[key]; !ok {
				t.Errorf("resources.%s missing", key)
			}
		}
	case <-time.After(3 * time.Second):
		t.Fatal("timed out waiting for first agent_heartbeat")
	}

	clientCancel()
	clientWG.Wait()
}

// TestLegacyRegisterAckTimeoutTriggersReconnect simulates a backend
// that accepts the WS upgrade and reads the agent_register frame but
// never replies with agent_register_ack. The bridge must close the
// connection within registerAckTimeout + slack and the reconnect loop
// must observe a disconnect.
func TestLegacyRegisterAckTimeoutTriggersReconnect(t *testing.T) {
	// Not parallel — we sample the global telemetry.WSDisconnects
	// counter and want a clean baseline.

	// Use a short ack timeout for the test. We can't override the
	// package constant, so we rely on the real 5s value but cap test
	// runtime via a tight deadline.
	upgradeCount := atomic.Int64{}

	mux := http.NewServeMux()
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		conn, err := websocket.Accept(w, r, &websocket.AcceptOptions{
			InsecureSkipVerify: true,
		})
		if err != nil {
			t.Logf("accept error: %v", err)
			return
		}
		upgradeCount.Add(1)
		// Consume the agent_register frame but DO NOT ack.
		ctx := r.Context()
		_, _, _ = conn.Read(ctx)
		// Hold the connection until the bridge tears it down.
		<-ctx.Done()
		_ = conn.Close(websocket.StatusNormalClosure, "test done")
	})
	srv := httptest.NewServer(mux)
	defer srv.Close()

	wsURL := "ws" + strings.TrimPrefix(srv.URL, "http")

	disconnectsBefore := telemetry.WSDisconnects.Load()

	client := NewClient(wsURL)
	client.HostID = "timeout-host"
	client.Version = "v1"

	clientCtx, clientCancel := context.WithCancel(context.Background())
	defer clientCancel()

	// Run the client in a goroutine; we expect ack-timeout → reconnect
	// to fire within registerAckTimeout + initial backoff (~5.5s).
	clientWG := &sync.WaitGroup{}
	clientWG.Add(1)
	go func() {
		defer clientWG.Done()
		client.Run(clientCtx)
	}()

	// Wait for at least one disconnect to be recorded — meaning the
	// register-ack timeout caused connectAndPump to return with an
	// error and the reconnect path advanced the counter.
	deadline := time.After(registerAckTimeout + 3*time.Second)
	for {
		if telemetry.WSDisconnects.Load()-disconnectsBefore >= 1 {
			break
		}
		select {
		case <-deadline:
			t.Fatalf("ack timeout did not trigger reconnect: disconnects_delta=%d, upgrades=%d",
				telemetry.WSDisconnects.Load()-disconnectsBefore, upgradeCount.Load())
		case <-time.After(100 * time.Millisecond):
		}
	}

	// We should have observed at least one upgrade (the initial dial).
	// The reconnect path *may* race past us by the time we cancel —
	// but >= 1 is the structural assertion that matters.
	if upgradeCount.Load() < 1 {
		t.Errorf("expected at least 1 WS upgrade, got %d", upgradeCount.Load())
	}

	clientCancel()
	clientWG.Wait()
}
