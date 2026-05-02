// OpenTelemetry tracing setup for the rafraf-bridge (T2.1).
//
// Per docs/10_Production_Pivot_Spec.md §7.3, the production target is
// Grafana Cloud Tempo. This file installs an OTLP/HTTP exporter when
// OTEL_EXPORTER_OTLP_ENDPOINT is set; otherwise SetupTracing returns a
// no-op shutdown function so the bridge stays runnable in dev without
// any OTel collector running.
//
// The shutdown closure flushes the BatchSpanProcessor and shuts the
// provider down with a bounded context — main.go must defer it before
// process exit.
//
// Resource attributes follow OTel semconv:
//   - service.name        — supplied by caller (e.g. "rafraf-bridge")
//   - service.version     — supplied by caller (build version constant)
//   - deployment.environment — env OTEL_DEPLOYMENT_ENV (default "dev")
//   - host.name           — Mac hostname via os.Hostname()
package telemetry

import (
	"context"
	"fmt"
	"os"
	"strings"
	"time"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	semconv "go.opentelemetry.io/otel/semconv/v1.21.0"
)

// tracingShutdownTimeout caps how long the deferred Shutdown call in
// main.go waits for the BatchSpanProcessor to flush. 5s mirrors the
// metricsServerShutdownTimeout already used in this package so the
// bridge has a consistent shutdown budget.
const tracingShutdownTimeout = 5 * time.Second

// noopShutdown is returned when tracing is disabled. Defers in main.go
// can call it unconditionally.
func noopShutdown(_ context.Context) error { return nil }

// SetupTracing initialises a global OpenTelemetry TracerProvider and
// registers it via otel.SetTracerProvider so the rest of the bridge can
// pull tracers via otel.Tracer(name).
//
// Behaviour:
//   - If OTEL_EXPORTER_OTLP_ENDPOINT is empty, no provider is installed
//     and a no-op shutdown closure is returned. SetupTracing logs nothing
//     in this branch — the caller should treat the noop case as the
//     dev default.
//   - If the env var is set, an OTLP/HTTP exporter is wired with a
//     BatchSpanProcessor. OTEL_EXPORTER_OTLP_HEADERS (e.g.
//     "Authorization=Basic ABC") is parsed for Grafana Cloud auth.
//
// The returned shutdown func is non-nil in all cases (so callers can
// always `defer shutdown(ctx)`); if the underlying provider is the
// global no-op, shutdown is a noop.
func SetupTracing(ctx context.Context, serviceName, version string) (func(context.Context) error, error) {
	endpoint := strings.TrimSpace(os.Getenv("OTEL_EXPORTER_OTLP_ENDPOINT"))
	if endpoint == "" {
		return noopShutdown, nil
	}

	res, err := buildResource(ctx, serviceName, version)
	if err != nil {
		return noopShutdown, fmt.Errorf("telemetry: build resource: %w", err)
	}

	exporter, err := buildOTLPExporter(ctx, endpoint)
	if err != nil {
		return noopShutdown, fmt.Errorf("telemetry: build exporter: %w", err)
	}

	provider := sdktrace.NewTracerProvider(
		sdktrace.WithBatcher(exporter),
		sdktrace.WithResource(res),
	)
	otel.SetTracerProvider(provider)

	return func(shutdownCtx context.Context) error {
		ctxWithTimeout, cancel := context.WithTimeout(shutdownCtx, tracingShutdownTimeout)
		defer cancel()
		return provider.Shutdown(ctxWithTimeout)
	}, nil
}

// buildResource assembles the OTel Resource that decorates every span
// the bridge emits. Hostname lookup failures are non-fatal — the
// resource simply omits host.name in that case so observability still
// works in containerised environments where hostname resolution may be
// constrained.
func buildResource(ctx context.Context, serviceName, version string) (*resource.Resource, error) {
	environment := strings.TrimSpace(os.Getenv("OTEL_DEPLOYMENT_ENV"))
	if environment == "" {
		environment = "dev"
	}

	attrs := []attribute.KeyValue{
		semconv.ServiceName(serviceName),
		semconv.ServiceVersion(version),
		semconv.DeploymentEnvironment(environment),
	}

	if hostname, err := os.Hostname(); err == nil && hostname != "" {
		attrs = append(attrs, semconv.HostName(hostname))
	}

	return resource.New(ctx, resource.WithAttributes(attrs...))
}

// buildOTLPExporter constructs an OTLP/HTTP exporter targeting endpoint.
// OTEL_EXPORTER_OTLP_HEADERS is parsed for the Grafana Cloud
// Authorization header. The endpoint may be a full URL (e.g.
// https://otlp-gateway-prod-eu-west-2.grafana.net/otlp) or a host:port
// pair; otlptracehttp.WithEndpointURL handles either.
func buildOTLPExporter(ctx context.Context, endpoint string) (sdktrace.SpanExporter, error) {
	headers := parseHeaders(os.Getenv("OTEL_EXPORTER_OTLP_HEADERS"))

	opts := []otlptracehttp.Option{
		otlptracehttp.WithEndpointURL(endpoint),
	}
	if len(headers) > 0 {
		opts = append(opts, otlptracehttp.WithHeaders(headers))
	}

	return otlptracehttp.New(ctx, opts...)
}

// parseHeaders converts "k1=v1,k2=v2" into a map. Malformed entries are
// silently dropped so a typo in the env var cannot crash startup —
// OTel SDKs follow the same lenient policy.
func parseHeaders(raw string) map[string]string {
	out := map[string]string{}
	if raw == "" {
		return out
	}
	for _, chunk := range strings.Split(raw, ",") {
		chunk = strings.TrimSpace(chunk)
		if chunk == "" {
			continue
		}
		idx := strings.Index(chunk, "=")
		if idx <= 0 {
			continue
		}
		key := strings.TrimSpace(chunk[:idx])
		val := strings.TrimSpace(chunk[idx+1:])
		if key == "" {
			continue
		}
		out[key] = val
	}
	return out
}
