// HTTP debug surface for the bridge.
//
// Per docs/11_Bridge_Spec.md §9, /debug/vars exposes the expvar registry
// populated in metrics.go. Per §12.1 the listener defaults to
// 127.0.0.1:9090 and is gated by [telemetry] expvar_enabled. This file
// implements the minimal mux + lifecycle helpers; cmd/bridge will wire
// the Start/Shutdown calls in T0.5.13.
package telemetry

import (
	"context"
	"encoding/json"
	"errors"
	"expvar"
	"log/slog"
	"net"
	"net/http"
	"os/exec"
	"sync/atomic"
	"time"
)

// metricsServerShutdownTimeout caps how long Shutdown waits for in-flight
// /debug/vars or /healthz handlers to drain. The endpoints are read-only
// and serve quickly, so 5s is comfortably more than enough.
const metricsServerShutdownTimeout = 5 * time.Second

// StartMetricsServer mounts /debug/vars (the expvar registry) and /healthz
// on addr and starts serving in a background goroutine. The listener is
// bound synchronously before returning so callers can rely on
// server.Addr — useful for tests that pass ":0" and need to discover the
// chosen port.
//
// An empty addr disables the surface entirely and returns (nil, nil); cmd/bridge
// passes an empty string when [telemetry] expvar_enabled is false.
func StartMetricsServer(addr string, logger *slog.Logger) (*http.Server, error) {
	if addr == "" {
		return nil, nil
	}
	if logger == nil {
		logger = slog.Default()
	}

	mux := http.NewServeMux()
	mux.Handle("/debug/vars", expvar.Handler())
	mux.HandleFunc("/healthz", healthzHandler)

	listener, err := net.Listen("tcp", addr)
	if err != nil {
		return nil, err
	}

	server := &http.Server{
		Addr:              listener.Addr().String(),
		Handler:           mux,
		ReadHeaderTimeout: 5 * time.Second,
	}

	go func() {
		logger.Info("telemetry server starting", "addr", server.Addr)
		if err := server.Serve(listener); err != nil && !errors.Is(err, http.ErrServerClosed) {
			logger.Error("telemetry server failed", "err", err)
		}
	}()

	return server, nil
}

// ShutdownMetricsServer gracefully shuts down the metrics server with a
// bounded timeout. A nil server is treated as "already disabled" and
// returns nil; this lets cmd/bridge call ShutdownMetricsServer
// unconditionally during shutdown without first checking
// [telemetry] expvar_enabled.
func ShutdownMetricsServer(ctx context.Context, server *http.Server) error {
	if server == nil {
		return nil
	}
	shutdownCtx, cancel := context.WithTimeout(ctx, metricsServerShutdownTimeout)
	defer cancel()
	return server.Shutdown(shutdownCtx)
}

// claudeBinaryLookup resolves the on-disk path of the claude CLI. Tests
// override this swap-in to inject deterministic results without depending
// on the runner's PATH. Defaults to exec.LookPath which is the production
// behaviour.
var claudeBinaryLookup atomic.Pointer[func(string) (string, error)]

// claudeBinaryName is the executable name probed by /healthz. The launchd
// plist guarantees claude is on PATH, so a bare name is sufficient. If a
// future deployment needs a fixed path, swap claudeBinaryLookup.
const claudeBinaryName = "claude"

func lookupClaudeBinary(name string) (string, error) {
	if p := claudeBinaryLookup.Load(); p != nil {
		return (*p)(name)
	}
	return exec.LookPath(name)
}

// SetClaudeBinaryLookup overrides the function used by /healthz to detect
// the claude CLI. Provided primarily for tests; production code should
// leave the default in place. Pass nil to restore the default.
func SetClaudeBinaryLookup(fn func(string) (string, error)) {
	if fn == nil {
		claudeBinaryLookup.Store(nil)
		return
	}
	claudeBinaryLookup.Store(&fn)
}

// healthzPayload is the JSON body returned by /healthz. Per Doc 10 §8 the
// fields surface the build version (so the launchd KeepAlive probe can
// distinguish stale binaries) and whether the claude CLI is on PATH (so
// monitoring catches a broken install before the next subprocess spawn).
type healthzPayload struct {
	Status              string `json:"status"`
	Service             string `json:"service"`
	Version             string `json:"version"`
	ClaudeBinaryPresent bool   `json:"claude_binary_present"`
}

// healthzHandler returns a small JSON body the launchd KeepAlive probe and
// monitoring scripts can hit. Per Doc 10 §8 (Faz 2) we include enough
// signal to detect a bad install (claude binary missing) without doing
// any network IO — heavier checks (auth state, recent rate-limit) belong
// on dedicated endpoints so this probe stays cheap.
func healthzHandler(w http.ResponseWriter, _ *http.Request) {
	version := ""
	if p := bridgeVersion.Load(); p != nil {
		version = *p
	}

	_, err := lookupClaudeBinary(claudeBinaryName)
	payload := healthzPayload{
		Status:              "ok",
		Service:             "rafraf-bridge",
		Version:             version,
		ClaudeBinaryPresent: err == nil,
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	// Discard encoder errors: the response writer is the only sink and a
	// flush failure here cannot be recovered from anyway.
	_ = json.NewEncoder(w).Encode(payload)
}
