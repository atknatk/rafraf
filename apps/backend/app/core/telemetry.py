"""OpenTelemetry tracing wiring for the backend (T2.1).

Per docs/10_Production_Pivot_Spec.md §7.3 the production observability
target is Grafana Cloud Tempo. This module sets up an OpenTelemetry
``TracerProvider`` with sane defaults so the rest of the codebase can
import :func:`get_tracer` without worrying about initialization.

Behaviour:
    * If ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set, an OTLP HTTP exporter
      is wired with a :class:`BatchSpanProcessor`. ``OTEL_EXPORTER_OTLP_HEADERS``
      is parsed for Grafana Cloud auth (e.g.
      ``"Authorization=Basic xyz"``).
    * If ``OTEL_EXPORTER_OTLP_ENDPOINT`` is empty/unset, a
      :class:`ConsoleSpanExporter` is wired so spans land on stdout in dev.
    * :func:`setup_tracing` is idempotent. Subsequent calls with the same
      service name are no-ops; this matters for the FastAPI lifespan
      handler which may run multiple times under uvicorn's reload mode.

Resource attributes (per OTel semconv):
    * ``service.name`` — defaults to ``rafraf-backend``.
    * ``service.version`` — env ``OTEL_SERVICE_VERSION`` (default ``v1.0.0``).
    * ``deployment.environment`` — env ``OTEL_DEPLOYMENT_ENV`` (default ``dev``).
"""

from __future__ import annotations

import os

import structlog
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)
from opentelemetry.trace import Tracer

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

# Module-level guard so :func:`setup_tracing` is idempotent. We compare on
# (service_name, exporter_kind) rather than a plain bool so a future test
# that wants to reinitialize with a different exporter (e.g. swap console
# for OTLP) keeps working.
_initialized: tuple[str, str] | None = None


def _parse_headers(raw: str | None) -> dict[str, str]:
    """Parse OTLP headers env var ("k1=v1,k2=v2") into a dict.

    Empty / unset values yield an empty dict. Malformed entries (no ``=``)
    are silently dropped so a typo in the env var doesn't crash startup.
    """
    if not raw:
        return {}
    headers: dict[str, str] = {}
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk or "=" not in chunk:
            continue
        key, _, value = chunk.partition("=")
        headers[key.strip()] = value.strip()
    return headers


def _build_resource(service_name: str) -> Resource:
    """Build a :class:`Resource` from env-driven attributes."""
    version = os.getenv("OTEL_SERVICE_VERSION", "v1.0.0")
    environment = os.getenv("OTEL_DEPLOYMENT_ENV", "dev")
    return Resource.create(
        {
            "service.name": service_name,
            "service.version": version,
            "deployment.environment": environment,
        }
    )


def setup_tracing(service_name: str = "rafraf-backend") -> None:
    """Initialize a global :class:`TracerProvider` for the backend.

    Safe to call multiple times — subsequent invocations with the same
    service name are no-ops. The exporter is selected from
    ``OTEL_EXPORTER_OTLP_ENDPOINT``: when set we use the OTLP HTTP
    exporter (Grafana Cloud Tempo target); when empty we fall back to
    the console exporter so spans are visible in dev logs.
    """
    global _initialized

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    exporter_kind = "otlp" if endpoint else "console"
    desired = (service_name, exporter_kind)
    if _initialized == desired:
        return

    resource = _build_resource(service_name)
    provider = TracerProvider(resource=resource)

    if endpoint:
        headers = _parse_headers(os.getenv("OTEL_EXPORTER_OTLP_HEADERS"))
        otlp_exporter = OTLPSpanExporter(endpoint=endpoint, headers=headers)
        provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
        logger.info(
            "otel_tracing_initialized",
            service=service_name,
            exporter="otlp",
            endpoint=endpoint,
        )
    else:
        # Dev fallback — SimpleSpanProcessor keeps stdout output deterministic
        # for local debugging. BatchSpanProcessor would buffer and flush on
        # shutdown only, hiding spans during a single request lifecycle.
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
        logger.info(
            "otel_tracing_initialized",
            service=service_name,
            exporter="console",
        )

    trace.set_tracer_provider(provider)
    _initialized = desired


def get_tracer(name: str) -> Tracer:
    """Return a :class:`Tracer` for the given module name.

    Thin wrapper around :func:`opentelemetry.trace.get_tracer` so callers
    don't need to import the OTel API package directly. The name argument
    is conventionally the module's ``__name__``.
    """
    return trace.get_tracer(name)


def reset_for_testing() -> None:
    """Reset the module-level guard so tests can reinitialize.

    Production code never calls this. Test fixtures use it to swap the
    provider between tests without mutating OTel internals directly.
    """
    global _initialized
    _initialized = None
