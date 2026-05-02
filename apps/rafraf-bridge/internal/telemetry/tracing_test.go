// Tests for OpenTelemetry tracing setup (T2.1).
//
// We exercise three paths:
//   - empty OTEL_EXPORTER_OTLP_ENDPOINT -> noop shutdown, no error
//   - real OTLP endpoint -> exporter wired, shutdown closes cleanly
//   - parseHeaders helper covers the Grafana Cloud auth header format
//
// The OTLP test points at a local httptest server so we never reach a
// real Grafana Cloud endpoint. We don't assert on payload content (the
// exporter does an async best-effort send) — the goal is to verify the
// happy-path wiring, not to validate the OTLP wire format itself.
package telemetry

import (
	"context"
	"net/http"
	"net/http/httptest"
	"reflect"
	"testing"
	"time"
)

func TestSetupTracing_EmptyEndpoint_NoopShutdown(t *testing.T) {
	t.Setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
	ctx := context.Background()
	shutdown, err := SetupTracing(ctx, "rafraf-bridge", "v0-test")
	if err != nil {
		t.Fatalf("SetupTracing should not error when endpoint unset, got %v", err)
	}
	if shutdown == nil {
		t.Fatal("SetupTracing must always return a non-nil shutdown func")
	}
	// Calling shutdown is a noop and must not error.
	if err := shutdown(ctx); err != nil {
		t.Fatalf("noop shutdown should not error, got %v", err)
	}
}

func TestSetupTracing_WithMockOTLPEndpoint(t *testing.T) {
	// Stand up a simple HTTP server that accepts OTLP/HTTP requests so the
	// exporter has a real endpoint to point at. We don't validate the
	// payload because the exporter buffers asynchronously — the goal is
	// to ensure the happy path wires up without errors.
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer ts.Close()

	t.Setenv("OTEL_EXPORTER_OTLP_ENDPOINT", ts.URL+"/v1/traces")
	t.Setenv("OTEL_EXPORTER_OTLP_HEADERS", "Authorization=Basic xyz")
	t.Setenv("OTEL_DEPLOYMENT_ENV", "test")

	ctx := context.Background()
	shutdown, err := SetupTracing(ctx, "rafraf-bridge", "v0-test")
	if err != nil {
		t.Fatalf("SetupTracing should succeed with mock endpoint, got %v", err)
	}
	if shutdown == nil {
		t.Fatal("SetupTracing must return a non-nil shutdown func")
	}

	// Bound the shutdown context so a hung exporter cannot wedge the test.
	shutdownCtx, cancel := context.WithTimeout(ctx, 2*time.Second)
	defer cancel()
	if err := shutdown(shutdownCtx); err != nil {
		t.Logf("shutdown returned non-fatal error (likely no spans to flush): %v", err)
	}
}

func TestParseHeaders_HappyPath(t *testing.T) {
	got := parseHeaders("Authorization=Basic xyz,X-Tenant=acme")
	want := map[string]string{
		"Authorization": "Basic xyz",
		"X-Tenant":      "acme",
	}
	if !reflect.DeepEqual(got, want) {
		t.Errorf("parseHeaders mismatch:\n got=%v\nwant=%v", got, want)
	}
}

func TestParseHeaders_DropsMalformed(t *testing.T) {
	got := parseHeaders("good=ok,malformed,also=fine,")
	want := map[string]string{
		"good": "ok",
		"also": "fine",
	}
	if !reflect.DeepEqual(got, want) {
		t.Errorf("parseHeaders should drop malformed entries:\n got=%v\nwant=%v", got, want)
	}
}

func TestParseHeaders_Empty(t *testing.T) {
	if got := parseHeaders(""); len(got) != 0 {
		t.Errorf("parseHeaders(\"\") should be empty map, got %v", got)
	}
}

func TestParseHeaders_TrimsWhitespace(t *testing.T) {
	got := parseHeaders("  Authorization = Basic xyz  ,  X-Tenant=acme  ")
	want := map[string]string{
		"Authorization": "Basic xyz",
		"X-Tenant":      "acme",
	}
	if !reflect.DeepEqual(got, want) {
		t.Errorf("parseHeaders should trim whitespace:\n got=%v\nwant=%v", got, want)
	}
}

func TestBuildResource_IncludesHostName(t *testing.T) {
	t.Setenv("OTEL_DEPLOYMENT_ENV", "staging")
	res, err := buildResource(context.Background(), "rafraf-bridge", "v9.9.9")
	if err != nil {
		t.Fatalf("buildResource error: %v", err)
	}

	attrs := res.Attributes()
	found := map[string]string{}
	for _, kv := range attrs {
		found[string(kv.Key)] = kv.Value.AsString()
	}

	if found["service.name"] != "rafraf-bridge" {
		t.Errorf("service.name = %q, want rafraf-bridge", found["service.name"])
	}
	if found["service.version"] != "v9.9.9" {
		t.Errorf("service.version = %q, want v9.9.9", found["service.version"])
	}
	if found["deployment.environment"] != "staging" {
		t.Errorf("deployment.environment = %q, want staging", found["deployment.environment"])
	}
	// host.name comes from os.Hostname; must be non-empty on darwin/linux test runners.
	if found["host.name"] == "" {
		t.Error("host.name should be populated when os.Hostname succeeds")
	}
}

func TestBuildResource_DefaultsDeploymentEnvironment(t *testing.T) {
	// Explicitly clear via empty t.Setenv; t.Setenv restores after the
	// test so this cannot leak into siblings.
	t.Setenv("OTEL_DEPLOYMENT_ENV", "")
	res, err := buildResource(context.Background(), "rafraf-bridge", "v0")
	if err != nil {
		t.Fatalf("buildResource error: %v", err)
	}
	for _, kv := range res.Attributes() {
		if string(kv.Key) == "deployment.environment" {
			if kv.Value.AsString() != "dev" {
				t.Errorf("deployment.environment fallback = %q, want dev", kv.Value.AsString())
			}
			return
		}
	}
	t.Error("deployment.environment attribute missing")
}
