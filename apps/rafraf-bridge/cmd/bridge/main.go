// Command bridge is the entrypoint for the rafraf-bridge daemon.
//
// T0.5.13 replaces the CLI-flag-based test scaffolding with the full
// config-driven wiring described in docs/11_Bridge_Spec.md §3 and §12.
// On startup the bridge loads its TOML config, initialises a structured
// logger and the optional /debug/vars metrics surface, then runs four
// background loops in lock-step:
//
//   - ws.Client.Run             — outbound WebSocket pump.
//   - storage.Watcher.Run       — fsnotify tail of ~/.claude/projects/.
//   - statusline.Watcher.Run    — periodic ~/.claude/usage.json poller.
//   - inboundDispatcher loop    — drains ws.Client.In and routes
//     command.claude.run frames to claude.Runner.
//
// SIGINT / SIGTERM cancel the shared context; the dispatchers drain,
// the metrics server is shut down with a 5s timeout, and the bridge
// exits cleanly.
//
// The wsEventSink adapter (introduced in T0.5.5) is unchanged — it
// translates each typed claude.EventSink callback into a protocol
// envelope on its way to ws.Client.Send. This file additionally
// defines wsStorageSink (storage.Sink → ws) and wsUsageSink
// (statusline.UsageSink → ws) so the two background watchers feed the
// same egress channel.
package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"sync"
	"syscall"
	"time"

	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/claude"
	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/config"
	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/permission"
	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/protocol"
	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/statusline"
	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/storage"
	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/telemetry"
	"github.com/atknatk/rafraf/apps/rafraf-bridge/internal/ws"
)

const (
	defaultConfigPath       = "~/.config/rafraf-bridge/config.toml"
	uptimeTickInterval      = 1 * time.Second
	metricsTickInterval     = 15 * time.Second
	telemetryShutdownGrace  = 5 * time.Second
	postShutdownDrainPause  = 200 * time.Millisecond
	authCheckTimeoutSeconds = 10
	// staleArtifactMaxAge is the threshold above which the V1.2
	// startup sweep deletes leftover settings overlays from prior
	// crashed bridge runs.
	staleArtifactMaxAge = time.Hour
	// permissionHookSibling is the file name of the hook binary
	// shipped alongside the bridge binary. The runner resolves it via
	// os.Executable() + sibling lookup at startup.
	permissionHookSibling = "rafraf-perm-hook"
)

// run is the testable entrypoint. It returns the desired process exit code
// so main() stays a single-liner; tests in T0.5.13+ may invoke run with a
// stub argv to exercise the --check/--version branches without spawning a
// subprocess.
func run(args []string) int {
	fs := flag.NewFlagSet("rafraf-bridge", flag.ContinueOnError)
	configPath := fs.String("config", defaultConfigPath, "path to config TOML")
	showVersion := fs.Bool("version", false, "print version and exit")
	checkOnly := fs.Bool("check", false, "load + validate config then exit")
	if err := fs.Parse(args); err != nil {
		return 2
	}

	if *showVersion {
		fmt.Printf("rafraf-bridge %s\n", Version)
		return 0
	}

	cfg, err := config.Load(*configPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "config load failed: %v\n", err)
		return 1
	}
	if *checkOnly {
		fmt.Printf("config OK: %s\n", *configPath)
		return 0
	}

	logger := telemetry.NewLogger(cfg.Telemetry.LogLevel)
	telemetry.SetBridgeVersion(Version)
	// T2.2: stamp the Prometheus collector with (bridge_version, host_id)
	// so multi-bridge scrapes attribute samples without relabel rules.
	// Hostname is the canonical bridge identity today; if os.Hostname()
	// fails we fall through to the "unknown" sentinel set inside the
	// telemetry package so /metrics still serves a usable body.
	hostName, hostErr := os.Hostname()
	if hostErr != nil || hostName == "" {
		hostName = "unknown"
	}
	telemetry.SetPromIdentity(Version, hostName)

	logger.Info("rafraf-bridge starting",
		"version", Version,
		"backend_url", cfg.BackendURL,
		"config_path", *configPath,
	)

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// OpenTelemetry tracing (T2.1). A failure to wire the OTLP exporter
	// is non-fatal — tracing is optional and the bridge must keep
	// running so claude RPCs remain serviceable. If
	// OTEL_EXPORTER_OTLP_ENDPOINT is unset the returned shutdown
	// function is a noop.
	tracingShutdown, tracingErr := telemetry.SetupTracing(ctx, "rafraf-bridge", Version)
	if tracingErr != nil {
		logger.Warn("opentelemetry tracing setup failed", "err", tracingErr)
	}
	defer func() {
		shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), telemetryShutdownGrace)
		defer shutdownCancel()
		if err := tracingShutdown(shutdownCtx); err != nil {
			logger.Warn("opentelemetry tracing shutdown error", "err", err)
		}
	}()

	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
	go func() {
		select {
		case sig := <-sigCh:
			logger.Info("signal received, shutting down", "signal", sig.String())
			cancel()
		case <-ctx.Done():
		}
	}()

	// Optional /debug/vars + /healthz HTTP surface.
	var metricsServer *http.Server
	if cfg.Telemetry.ExpvarEnabled {
		srv, srvErr := telemetry.StartMetricsServer(cfg.Telemetry.ExpvarAddr, logger)
		if srvErr != nil {
			logger.Error("telemetry server start failed", "err", srvErr, "addr", cfg.Telemetry.ExpvarAddr)
			// Non-fatal: continue without /debug/vars.
		} else {
			metricsServer = srv
		}
	}

	// WebSocket client (outbound to control plane).
	wsClient := ws.NewClient(cfg.BackendURL)

	// Claude subprocess runner.
	runner := claude.NewRunner(cfg, logger)

	// V1.2 — start the permission Broker + UDS listener and wire it
	// into the runner so the per-session settings overlay can register
	// the PreToolUse hook.
	//
	// The startup sweep drops leftover sock + settings files from a
	// previously crashed bridge before we bind our own socket. Failures
	// are non-fatal: the broker also reclaims a stale socket on bind.
	permission.SweepStaleArtifacts(logger, "", staleArtifactMaxAge)
	broker, brokerErr := permission.NewBroker("", logger)
	if brokerErr != nil {
		// Broker startup failure is degraded-mode but not fatal —
		// without it tool calls flow without approval prompts (the
		// runner skips --settings injection). The operator must
		// restart to recover. Log loudly.
		logger.Error("permission broker startup failed; running without approval hook",
			"err", brokerErr,
		)
	} else {
		if err := broker.Start(ctx); err != nil {
			logger.Error("permission broker start failed", "err", err)
		}
		hookPath := resolvePermissionHookPath(logger)
		runner.SetPermissionContext(broker.Sock(), hookPath)
		logger.Info("permission broker wired into runner",
			"sock", broker.Sock(),
			"hook", hookPath,
		)
	}
	defer func() {
		if broker != nil {
			if err := broker.Close(); err != nil {
				logger.Warn("permission broker close error", "err", err)
			}
		}
	}()

	// Pre-flight auth check. A failure is non-fatal — the bridge stays
	// alive so the operator can refresh `claude login` without restarting
	// the daemon. We surface event.bridge.auth_expired so the control
	// plane can inform the user surface.
	startAuthProbe(ctx, runner, wsClient, logger)

	// Storage watcher (optional).
	var storageWatcher *storage.Watcher
	if cfg.StorageWatcher.Enabled {
		storageWatcher = storage.NewWatcher(cfg, logger)
	}

	// Statusline watcher (optional).
	var statuslineWatcher *statusline.Watcher
	if cfg.Statusline.Enabled {
		statuslineWatcher = statusline.NewWatcher(cfg, logger)
	}

	// Wire all background loops. We use a sync.WaitGroup rather than an
	// errgroup because each loop has a different "expected" exit error
	// (ctx.Err for the watchers, no error for ws.Run) and we do not want
	// the first one to win to short-circuit shutdown of the others.
	var wg sync.WaitGroup

	wg.Add(1)
	go func() {
		defer wg.Done()
		wsClient.Run(ctx)
	}()

	wg.Add(1)
	go runUptimeTicker(ctx, &wg)

	wg.Add(1)
	go runMetricsPrinter(ctx, &wg, logger)

	if storageWatcher != nil {
		wg.Add(1)
		go func() {
			defer wg.Done()
			sink := newWSStorageSink(wsClient)
			if rerr := storageWatcher.Run(ctx, sink); rerr != nil && !errors.Is(rerr, context.Canceled) {
				logger.Warn("storage watcher exited", "err", rerr)
			}
		}()
	}

	if statuslineWatcher != nil {
		wg.Add(1)
		go func() {
			defer wg.Done()
			sink := newWSUsageSink(wsClient)
			if rerr := statuslineWatcher.Run(ctx, sink); rerr != nil && !errors.Is(rerr, context.Canceled) {
				logger.Warn("statusline watcher exited", "err", rerr)
			}
		}()
	}

	// Inbound dispatcher: single consumer of ws.Client.Inbound. V1.1 wired
	// the channel + JSON decode in the ws reader; this loop fans frames
	// into dispatchCommand. Each handler is required to be non-blocking
	// (synchronous work must be moved into a goroutine) so a slow handler
	// cannot back up the bounded Inbound buffer — V1.3 broker.Resolve
	// must follow the same contract.
	wg.Add(1)
	go func() {
		defer wg.Done()
		runInboundDispatcher(ctx, runner, wsClient, logger)
	}()

	logger.Info("rafraf-bridge ready",
		"storage_enabled", cfg.StorageWatcher.Enabled,
		"statusline_enabled", cfg.Statusline.Enabled,
		"expvar_enabled", cfg.Telemetry.ExpvarEnabled,
	)

	// Block until ctx is cancelled by signal handler.
	<-ctx.Done()

	// Shutdown sequence: telemetry first (its handlers may briefly hold
	// references to the in-flight context), then wait for goroutines to
	// observe the cancellation, then a tiny drain pause so the WS pump
	// can flush its terminal envelopes.
	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), telemetryShutdownGrace)
	defer shutdownCancel()
	if shErr := telemetry.ShutdownMetricsServer(shutdownCtx, metricsServer); shErr != nil {
		logger.Warn("telemetry server shutdown error", "err", shErr)
	}

	wgDone := make(chan struct{})
	go func() {
		wg.Wait()
		close(wgDone)
	}()
	select {
	case <-wgDone:
	case <-time.After(telemetryShutdownGrace):
		logger.Warn("background goroutines did not exit within grace window")
	}

	time.Sleep(postShutdownDrainPause)
	logger.Info("rafraf-bridge stopped")
	return 0
}

func main() {
	os.Exit(run(os.Args[1:]))
}

// startAuthProbe runs claude.AuthCheck with a bounded timeout. A failure
// emits event.bridge.auth_expired so the control plane (and ultimately
// the iOS app) can prompt the user to re-login. The bridge keeps running
// in either case — the operator can re-issue `claude login` without
// restarting the daemon.
func startAuthProbe(ctx context.Context, runner *claude.Runner, wsClient *ws.Client, logger *slog.Logger) {
	probeCtx, cancel := context.WithTimeout(ctx, authCheckTimeoutSeconds*time.Second)
	defer cancel()

	if err := runner.AuthCheck(probeCtx); err != nil {
		logger.Warn("claude auth check failed at startup", "err", err)
		telemetry.ClaudeAuthExpired.Add(1)
		env, buildErr := protocol.NewEventBridgeAuthExpired("", "", protocol.EventBridgeAuthExpired{
			Reason: err.Error(),
		})
		if buildErr != nil {
			logger.Error("failed to build auth_expired envelope", "err", buildErr)
			return
		}
		wsClient.Send(env)
		return
	}
	logger.Info("claude auth check ok")
}

// runUptimeTicker keeps telemetry.BridgeUptimeSeconds fresh so /debug/vars
// readers see a live counter without the bridge having to publish a custom
// expvar.Func that calls time.Since on every read.
func runUptimeTicker(ctx context.Context, wg *sync.WaitGroup) {
	defer wg.Done()
	start := time.Now()
	t := time.NewTicker(uptimeTickInterval)
	defer t.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-t.C:
			telemetry.BridgeUptimeSeconds.Store(int64(time.Since(start).Seconds()))
		}
	}
}

// runMetricsPrinter logs the single-line metrics summary every
// metricsTickInterval. Routed through the structured logger so log
// shippers can ingest it without a separate text-vs-json split.
func runMetricsPrinter(ctx context.Context, wg *sync.WaitGroup, logger *slog.Logger) {
	defer wg.Done()
	t := time.NewTicker(metricsTickInterval)
	defer t.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-t.C:
			logger.Info("metrics", "snapshot", telemetry.FormatMetricsLine())
		}
	}
}

// runInboundDispatcher drains ws.Client.Inbound and routes command.*
// frames to the runner via dispatchCommand. The ws.Client reader
// goroutine decodes each WSS frame into a protocol.Envelope and fans
// it through the bounded Inbound channel; this loop is the single
// consumer.
//
// V1.1 wires the plumbing for command.claude.run / command.claude.abort
// (already supported by dispatchCommand) and is the foundation for the
// permission RPCs added in V1.3 (command.claude.permission.allow|deny).
// Until V1.3 lands those RPC types fall through dispatchCommand's
// default branch which logs at debug level — that is the safe
// degradation behaviour spelled out in the design doc §4.4.
func runInboundDispatcher(ctx context.Context, runner *claude.Runner, wsClient *ws.Client, logger *slog.Logger) {
	logger.Debug("inbound dispatcher started",
		"inbound_capacity", cap(wsClient.Inbound),
	)
	for {
		select {
		case <-ctx.Done():
			return
		case env, ok := <-wsClient.Inbound:
			if !ok {
				return
			}
			dispatchCommand(ctx, runner, wsClient, logger, env)
		}
	}
}

// dispatchCommand routes a parsed command.* envelope to the runner. It is
// invoked from runInboundDispatcher once the ws.Client surfaces inbound
// frames. Kept as a free function so tests can exercise the routing
// without spinning up the full process.
func dispatchCommand(ctx context.Context, runner *claude.Runner, wsClient *ws.Client, logger *slog.Logger, env protocol.Envelope) {
	switch env.Type {
	case protocol.TypeCommandClaudeRun:
		var cmd protocol.CommandClaudeRun
		if err := json.Unmarshal(env.Payload, &cmd); err != nil {
			logger.Warn("dispatch: invalid command.claude.run payload", "err", err, "id", env.ID)
			return
		}
		req := claude.RunRequest{
			Prompt:         cmd.Prompt,
			PermissionMode: cmd.PermissionMode,
			UserID:         cmd.UserID,
		}
		if cmd.SessionID != nil {
			req.SessionID = *cmd.SessionID
		}
		if cmd.AgentTeams != nil {
			req.AgentTeams = *cmd.AgentTeams
		}
		if cmd.ProjectDir != nil {
			req.ProjectDir = *cmd.ProjectDir
		}
		sink := &wsEventSink{ws: wsClient, correlationID: env.CorrelationID}
		go func() {
			if err := runner.Run(ctx, req, sink); err != nil {
				logger.Warn("claude runner exited with error",
					"err", err,
					"session_id", req.SessionID,
					"correlation_id", env.CorrelationID,
				)
			}
		}()
	case protocol.TypeCommandClaudeAbort:
		var cmd protocol.CommandClaudeAbort
		if err := json.Unmarshal(env.Payload, &cmd); err != nil {
			logger.Warn("dispatch: invalid command.claude.abort payload", "err", err, "id", env.ID)
			return
		}
		// runner.Abort blocks for ~100ms (abortGracePeriod). Spawn a
		// goroutine so back-to-back aborts do not wedge the bounded
		// Inbound buffer. Abort is idempotent + thread-safe.
		go func() {
			if err := runner.Abort(cmd.SessionID); err != nil {
				logger.Warn("abort failed", "err", err, "session_id", cmd.SessionID)
			}
		}()
	default:
		logger.Debug("dispatch: ignoring envelope", "type", env.Type, "id", env.ID)
	}
}

// ---------------------------------------------------------------------------
// Sink adapters — pipe each watcher's typed callback into ws.Client.Send.
// ---------------------------------------------------------------------------

// wsEventSink adapts the typed claude.EventSink contract to the bridge's
// WebSocket egress. Each callback marshals its payload into a protocol
// envelope (using the package builders so type tags can never drift) and
// hands it to ws.Client.Send.
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

// wsStorageSink adapts storage.Sink to ws.Client.Send.
type wsStorageSink struct {
	ws *ws.Client
}

func newWSStorageSink(c *ws.Client) *wsStorageSink {
	return &wsStorageSink{ws: c}
}

func (s *wsStorageSink) target(sessionID string) string {
	if sessionID == "" {
		return ""
	}
	return "session:" + sessionID
}

func (s *wsStorageSink) OnAITitle(ev protocol.EventStorageAITitle) error {
	env, err := protocol.NewEventStorageAITitle(s.target(ev.SessionID), "", ev)
	if err != nil {
		return err
	}
	s.ws.Send(env)
	return nil
}

func (s *wsStorageSink) OnPRLink(ev protocol.EventStoragePRLink) error {
	env, err := protocol.NewEventStoragePRLink(s.target(ev.SessionID), "", ev)
	if err != nil {
		return err
	}
	s.ws.Send(env)
	return nil
}

func (s *wsStorageSink) OnHookAttachment(ev protocol.EventStorageHookAttachment) error {
	env, err := protocol.NewEventStorageHookAttachment(s.target(ev.SessionID), "", ev)
	if err != nil {
		return err
	}
	s.ws.Send(env)
	return nil
}

// resolvePermissionHookPath returns the absolute path to the
// rafraf-perm-hook binary that ships alongside the bridge. We
// discover it via os.Executable() + sibling lookup so the same
// resolution works in dev (running `go run ./cmd/bridge`), in a
// hand-built `make build` layout, and in the eventual `.pkg`
// install layout (/usr/local/bin/{rafraf-bridge,rafraf-perm-hook}).
//
// Returns "" when the sibling binary cannot be found; the runner
// then logs a warning and skips the --settings injection so dev
// without the hook still works.
func resolvePermissionHookPath(logger *slog.Logger) string {
	exe, err := os.Executable()
	if err != nil {
		logger.Warn("permission hook resolve: os.Executable failed",
			"err", err,
		)
		return ""
	}
	exeDir := filepath.Dir(exe)
	candidate := filepath.Join(exeDir, permissionHookSibling)
	if _, statErr := os.Stat(candidate); statErr == nil {
		return candidate
	}
	logger.Debug("permission hook resolve: sibling missing",
		"candidate", candidate,
	)
	return ""
}

// newWSUsageSink builds a statusline.UsageSink closure that forwards each
// EventUsageReport through wsClient.Send. Returning the closure (rather
// than a method-bearing struct) matches the statusline.UsageSink type
// signature exactly.
func newWSUsageSink(c *ws.Client) statusline.UsageSink {
	return func(ev protocol.EventUsageReport) {
		env, err := protocol.NewEventUsageReport("", "", ev)
		if err != nil {
			return
		}
		c.Send(env)
	}
}
