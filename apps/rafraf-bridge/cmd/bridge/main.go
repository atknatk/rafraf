// Command bridge is the entrypoint for the rafraf-bridge daemon.
//
// T0.5.2 splits the spike's single-file main.go (412 lines, see
// ~/Code/claude-teams-spike/bridge/main.go) into focused packages while
// preserving runtime behavior. CLI flags, signal handling and mode
// selection live here; everything else is delegated.
package main

import (
	"context"
	"flag"
	"fmt"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/claude"
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
		runTask(ctx, wsClient, *task, *cwd, *permMode)
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

func runTask(ctx context.Context, wsClient *ws.Client, task, cwd, permMode string) {
	runner := claude.NewRunner(task, cwd, permMode, wsClient.Send)

	wsClient.Send(protocol.Envelope{
		Type:    "event.bridge.task_started",
		ID:      protocol.NewID(),
		TS:      protocol.NowISO(),
		Payload: protocol.MustJSON(map[string]any{"prompt_len": len(task), "cwd": cwd}),
	})

	if err := runner.Run(ctx); err != nil {
		fmt.Fprintf(os.Stderr, "[runner] error: %v\n", err)
		wsClient.Send(protocol.Envelope{
			Type:    "event.bridge.task_completed",
			ID:      protocol.NewID(),
			TS:      protocol.NowISO(),
			Payload: protocol.MustJSON(map[string]any{"ok": false, "lines_read": telemetry.ClaudeLinesRead.Load()}),
		})
	} else {
		wsClient.Send(protocol.Envelope{
			Type:    "event.bridge.task_completed",
			ID:      protocol.NewID(),
			TS:      protocol.NowISO(),
			Payload: protocol.MustJSON(map[string]any{"ok": true, "lines_read": telemetry.ClaudeLinesRead.Load()}),
		})
	}

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
