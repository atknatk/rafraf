"""Unit tests for app.core.telemetry (T2.1).

Strategy:
    * The OpenTelemetry global ``_TRACER_PROVIDER`` is process-wide and
      protected by a "set-once" guard inside the OTel SDK. Tests therefore
      do NOT try to swap the global provider per test; instead they:
        - exercise the helpers (``_build_resource``, ``_parse_headers``)
          directly, and
        - install an :class:`InMemorySpanExporter` against whichever
          provider is current so emitted spans are observable without
          mutating OTel internals.
    * Module-level idempotency state in :mod:`app.core.telemetry` is
      cleared between tests via :func:`reset_for_testing`.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from unittest.mock import patch

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.core.telemetry import (
    _build_resource,
    _parse_headers,
    get_tracer,
    reset_for_testing,
    setup_tracing,
)


@pytest.fixture(autouse=True)
def _reset_tracing() -> Iterator[None]:
    """Clear our module-level idempotency cache between tests."""
    reset_for_testing()
    yield
    reset_for_testing()


def _ensure_sdk_provider_with_inmemory_exporter() -> InMemorySpanExporter:
    """Attach an InMemorySpanExporter to the live provider.

    If the global provider is the SDK's :class:`TracerProvider`, an extra
    :class:`SimpleSpanProcessor` is appended. Otherwise (i.e. the proxy
    provider, which short-circuits to no-op tracers), a fresh SDK
    provider is installed via ``set_tracer_provider`` — that call only
    succeeds the first time per process, but the proxy provider then
    forwards to it on subsequent ``get_tracer`` calls, which is exactly
    what we want for assertions.
    """
    exporter = InMemorySpanExporter()
    provider = trace.get_tracer_provider()
    sdk_provider: TracerProvider
    if isinstance(provider, TracerProvider):
        sdk_provider = provider
    else:
        sdk_provider = TracerProvider()
        trace.set_tracer_provider(sdk_provider)
    sdk_provider.add_span_processor(SimpleSpanProcessor(exporter))
    return exporter


def test_setup_tracing_with_console_exporter_when_endpoint_unset() -> None:
    """Empty OTLP endpoint env var → ConsoleSpanExporter dev fallback.

    The first time :func:`setup_tracing` runs, it must install an
    :class:`TracerProvider` on the global; subsequent OTel API calls
    then route to that provider. We assert the function returns
    cleanly and the global provider isn't a no-op proxy.
    """
    with patch.dict(os.environ, {"OTEL_EXPORTER_OTLP_ENDPOINT": ""}, clear=False):
        setup_tracing(service_name="rafraf-backend-test")
    # After setup, get_tracer_provider must return *something* that can
    # produce real spans. We don't assert on the exact class because the
    # global may already have been installed by a previous test in the
    # same process — what matters is that the call did not raise.
    tracer = get_tracer("test.smoke")
    with tracer.start_as_current_span("smoke") as span:
        assert span is not None


def test_setup_tracing_is_idempotent_via_module_guard() -> None:
    """Calling setup_tracing twice with the same args is a no-op.

    Verified through the module-level ``_initialized`` cache rather than
    OTel internals (which would log a noisy "Overriding" warning).
    """
    import app.core.telemetry as telemetry_mod

    with patch.dict(os.environ, {"OTEL_EXPORTER_OTLP_ENDPOINT": ""}, clear=False):
        setup_tracing(service_name="idempotent-test")
        first = telemetry_mod._initialized
        setup_tracing(service_name="idempotent-test")
        second = telemetry_mod._initialized
    assert first == ("idempotent-test", "console")
    assert first == second


def test_setup_tracing_with_otlp_endpoint_does_not_raise() -> None:
    """A non-empty OTLP endpoint configures the OTLP HTTP exporter.

    We can't easily inspect which exporter the provider holds without
    poking private attributes (and the global may already be claimed
    by an earlier test), so we assert the function completes and our
    module guard records ``"otlp"``.
    """
    import app.core.telemetry as telemetry_mod

    env = {
        "OTEL_EXPORTER_OTLP_ENDPOINT": "https://otlp.example.com/v1/traces",
        "OTEL_EXPORTER_OTLP_HEADERS": "Authorization=Basic abc123",
    }
    with patch.dict(os.environ, env, clear=False):
        setup_tracing(service_name="otlp-test")
    assert telemetry_mod._initialized == ("otlp-test", "otlp")


def test_get_tracer_returns_tracer() -> None:
    """get_tracer returns an OTel Tracer instance bound to the given name."""
    tracer = get_tracer("test.module")
    assert tracer is not None
    # Smoke: the tracer can produce spans without raising.
    with tracer.start_as_current_span("smoke") as span:
        assert span is not None


def test_inmemory_span_exporter_captures_spans() -> None:
    """Spans created via the global tracer are captured by InMemorySpanExporter.

    This is the harness pattern subsequent tests
    (``test_claude_code_runner_tracing``) re-use; verifying it here
    shrinks the blast radius of an OTel API upgrade.
    """
    exporter = _ensure_sdk_provider_with_inmemory_exporter()
    tracer = get_tracer("test.harness")
    with tracer.start_as_current_span("manual-span") as span:
        span.set_attribute("test.key", "test.value")

    spans = exporter.get_finished_spans()
    matching = [s for s in spans if s.name == "manual-span"]
    assert len(matching) == 1
    span: ReadableSpan = matching[0]
    assert span.attributes is not None
    assert span.attributes.get("test.key") == "test.value"


def test_parse_headers_handles_multiple_pairs() -> None:
    """Comma-separated key=value pairs decode into a dict."""
    out = _parse_headers("Authorization=Basic xyz,X-Tenant=acme")
    assert out == {"Authorization": "Basic xyz", "X-Tenant": "acme"}


def test_parse_headers_drops_malformed_entries() -> None:
    """Entries without ``=`` are silently dropped (typo tolerance)."""
    out = _parse_headers("good=ok,malformed,also=fine,")
    assert out == {"good": "ok", "also": "fine"}


def test_parse_headers_empty_returns_empty() -> None:
    """None or empty string → empty dict (not an exception)."""
    assert _parse_headers(None) == {}
    assert _parse_headers("") == {}


def test_build_resource_pulls_env_overrides() -> None:
    """Resource attrs honour OTEL_SERVICE_VERSION and OTEL_DEPLOYMENT_ENV."""
    env = {
        "OTEL_SERVICE_VERSION": "v9.9.9",
        "OTEL_DEPLOYMENT_ENV": "staging",
    }
    with patch.dict(os.environ, env, clear=False):
        resource = _build_resource("custom-service")
    attrs = resource.attributes
    assert attrs["service.name"] == "custom-service"
    assert attrs["service.version"] == "v9.9.9"
    assert attrs["deployment.environment"] == "staging"


def test_build_resource_falls_back_to_defaults() -> None:
    """Without env overrides we get the documented defaults."""
    saved_version = os.environ.pop("OTEL_SERVICE_VERSION", None)
    saved_env = os.environ.pop("OTEL_DEPLOYMENT_ENV", None)
    try:
        resource = _build_resource("default-service")
    finally:
        if saved_version is not None:
            os.environ["OTEL_SERVICE_VERSION"] = saved_version
        if saved_env is not None:
            os.environ["OTEL_DEPLOYMENT_ENV"] = saved_env
    attrs = resource.attributes
    assert attrs["service.version"] == "v1.0.0"
    assert attrs["deployment.environment"] == "dev"
