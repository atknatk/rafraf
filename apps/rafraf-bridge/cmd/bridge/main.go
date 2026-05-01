// Command bridge is the entrypoint for the rafraf-bridge daemon.
//
// T0.5.5 expanded internal/claude.Runner to the EventSink-driven contract
// described in docs/11_Bridge_Spec.md §3.4. This file owns the small
// wsEventSink adapter that wraps every typed callback into a protocol
// envelope and pushes it through the WebSocket client. Everything else
// (CLI flags, signal handling, soak/idle modes) is unchanged from T0.5.2.
package main

import (
	"context"
	"flag"
	"fmt"
	"log/slog"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/claude"
	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/config"
	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/protocol"
	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/telemetry"
	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/ws"
)

const (
	connectWaitAttempts  = 50
	connectWaitInterval  = 50 * time.Millisecond
	metricsTickInterval  = 15 * time.Second
	aliveTickInterval    = 60 * time.Second
	subprocessDrainPause = 500 * time.Millisecond
)

func main() {
	url := flag.String("url", "ws://localhost:8787", "control plane WebSocket URL")
	task := flag.String("task", "", "if set, run claude -p with this prompt and forward stream-json events")
	cwd := flag.String("cwd", "", "cwd for claude subprocess")
	permMode := flag.String("permission-mode", "", "claude --permission-mode value")
	soakSecs := flag.Int("soak-secs", 0, "if >0, stay alive for this many seconds, then exit (Test 7)")
	emitAlive := flag.Bool("emit-alive", false, "during soak, emit event.bridge.alive every 60s")
	showVersion := flag.Bool("version", false, "print version and exit")
	flag.Parse()

	if *showVersion {
		fmt.Printf("rafraf-bridge %s\n", Version)
		return
	}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// SIGINT / SIGTERM → context cancel.
	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
	go func() {
		<-sigCh
		cancel()
	}()

	logger := slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{Level: slog.LevelInfo}))

	wsClient := ws.NewClient(*url)
	go wsClient.Run(ctx)

	// Wait briefly for first connection (best-effort).
	for i := 0; i < connectWaitAttempts && telemetry.WSConnected.Load() == 0; i++ {
		time.Sleep(connectWaitInterval)
	}

	// Periodic metrics line on stderr.
	go runMetricsPrinter(ctx)

	switch {
	case *task != "":
		runTask(ctx, wsClient, logger, *task, *cwd, *permMode)
	case *soakSecs > 0:
		runSoak(ctx, wsClient, *soakSecs, *emitAlive)
	default:
		// No task, no soak → idle until SIGINT.
		<-ctx.Done()
	}
}

func runMetricsPrinter(ctx context.Context) {
	t := time.NewTicker(metricsTickInterval)
	defer t.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-t.C:
			fmt.Fprintln(os.Stderr, telemetry.FormatMetricsLine())
		}
	}
}

func runTask(ctx context.Context, wsClient *ws.Client, logger *slog.Logger, task, cwd, permMode string) {
	cfg := &config.Config{
		ClaudeBinary:   "claude",
		ProjectDir:     cwd,
		PermissionMode: permMode,
	}
	runner := claude.NewRunner(cfg, logger)
	sink := &wsEventSink{ws: wsClient}

	wsClient.Send(protocol.Envelope{
		Type:    "event.bridge.task_started",
		ID:      protocol.NewID(),
		TS:      protocol.NowISO(),
		Payload: protocol.MustJSON(map[string]any{"prompt_len": len(task), "cwd": cwd}),
	})

	err := runner.Run(ctx, claude.RunRequest{
		Prompt:         task,
		ProjectDir:     cwd,
		PermissionMode: permMode,
	}, sink)

	ok := err == nil
	if !ok {
		fmt.Fprintf(os.Stderr, "[runner] error: %v\n", err)
	}

	wsClient.Send(protocol.Envelope{
		Type:    "event.bridge.task_completed",
		ID:      protocol.NewID(),
		TS:      protocol.NowISO(),
		Payload: protocol.MustJSON(map[string]any{"ok": ok, "lines_read": telemetry.ClaudeLinesRead.Load()}),
	})

	// Drain a bit before exit so the WS pump can flush the final envelopes.
	time.Sleep(subprocessDrainPause)
}

func runSoak(ctx context.Context, wsClient *ws.Client, soakSecs int, emitAlive bool) {
	fmt.Fprintf(os.Stderr, "[soak] starting %d second soak\n", soakSecs)
	soakDeadline := time.Now().Add(time.Duration(soakSecs) * time.Second)
	alive := time.NewTicker(aliveTickInterval)
	defer alive.Stop()
	for time.Now().Before(soakDeadline) {
		select {
		case <-ctx.Done():
			return
		case <-time.After(time.Until(soakDeadline)):
			return
		case <-alive.C:
			if emitAlive {
				wsClient.Send(protocol.Envelope{
					Type:    "event.bridge.alive",
					ID:      protocol.NewID(),
					TS:      protocol.NowISO(),
					Payload: protocol.MustJSON(map[string]any{"ws_connected": telemetry.WSConnected.Load() == 1}),
				})
			}
		}
	}
}

// wsEventSink adapts the typed claude.EventSink contract to the bridge's
// WebSocket egress. Each callback marshals its payload into a protocol
// envelope (using the package builders so type tags can never drift) and
// hands it to ws.Client.Send. Marshalling errors are surfaced upward
// rather than swallowed so the runner can attribute them to the offending
// frame.
//
// Until T0.5.6 wires up the real parser these methods are unreachable in
// production paths; the adapter is here so the wiring is in place when
// the parser starts emitting events.
type wsEventSink struct {
	ws            *ws.Client
	correlationID string
}

func (s *wsEventSink) target(sessionID string) string {
	if sessionID == "" {
		return ""
	}
	return "session:" + sessionID
}

func (s *wsEventSink) emit(env protocol.Envelope, err error) error {
	if err != nil {
		return err
	}
	s.ws.Send(env)
	return nil
}

func (s *wsEventSink) OnInit(ev protocol.EventSessionInit) error {
	return s.emit(protocol.NewEventSessionInit(s.target(ev.SessionID), s.correlationID, ev))
}

func (s *wsEventSink) OnAssistant(ev protocol.EventSessionAssistant) error {
	return s.emit(protocol.NewEventSessionAssistant(s.target(ev.SessionID), s.correlationID, ev))
}

func (s *wsEventSink) OnUser(ev protocol.EventSessionUser) error {
	return s.emit(protocol.NewEventSessionUser(s.target(ev.SessionID), s.correlationID, ev))
}

func (s *wsEventSink) OnStream(ev protocol.EventSessionStream) error {
	return s.emit(protocol.NewEventSessionStream(s.target(ev.SessionID), s.correlationID, ev))
}

func (s *wsEventSink) OnTaskStarted(ev protocol.EventSessionTaskStarted) error {
	return s.emit(protocol.NewEventSessionTaskStarted(s.target(ev.SessionID), s.correlationID, ev))
}

func (s *wsEventSink) OnTaskProgress(ev protocol.EventSessionTaskProgress) error {
	return s.emit(protocol.NewEventSessionTaskProgress(s.target(ev.SessionID), s.correlationID, ev))
}

func (s *wsEventSink) OnTaskNotification(ev protocol.EventSessionTaskNotification) error {
	return s.emit(protocol.NewEventSessionTaskNotification(s.target(ev.SessionID), s.correlationID, ev))
}

func (s *wsEventSink) OnRateLimit(ev protocol.EventSessionRateLimit) error {
	return s.emit(protocol.NewEventSessionRateLimit(s.target(ev.SessionID), s.correlationID, ev))
}

func (s *wsEventSink) OnHookStarted(ev protocol.EventSessionHookStarted) error {
	return s.emit(protocol.NewEventSessionHookStarted(s.target(ev.SessionID), s.correlationID, ev))
}

func (s *wsEventSink) OnHookResponse(ev protocol.EventSessionHookResponse) error {
	return s.emit(protocol.NewEventSessionHookResponse(s.target(ev.SessionID), s.correlationID, ev))
}

func (s *wsEventSink) OnResult(ev protocol.EventSessionResult) error {
	return s.emit(protocol.NewEventSessionResult(s.target(ev.SessionID), s.correlationID, ev))
}
