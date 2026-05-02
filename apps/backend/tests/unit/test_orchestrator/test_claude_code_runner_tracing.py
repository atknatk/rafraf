"""OpenTelemetry tracing assertions for ClaudeCodeRunner (T2.1).

Strategy:
    * Reuse the synthetic ``_FakeRegistry`` pattern from
      ``test_claude_code_runner.py``: it captures the outbound RPC
      envelope and replays a canned event stream.
    * Attach an :class:`InMemorySpanExporter` to the live OTel provider
      so we can introspect the spans the runner emits.
    * Assert (a) ``claude.run`` parent span exists with the documented
      attributes, and (b) one ``claude.dispatch_event`` child per
      streamed event, with the matching ``claude.event_type`` attribute.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.orchestrator.claude_code_runner import ClaudeCodeRunner

# ---------------------------------------------------------------------------
# Test harness — minimal fakes lifted from test_claude_code_runner.
# ---------------------------------------------------------------------------


class _FakeRegistry:
    """Mimics the slice of BridgeRegistryService the runner depends on."""

    def __init__(
        self,
        *,
        events: list[dict[str, Any]] | None = None,
        send_succeeds: bool = True,
        online_host: str | None = "mac-1",
    ) -> None:
        self._events = list(events or [])
        self._send_succeeds = send_succeeds
        self._online_host = online_host
        self.last_envelope: dict[str, Any] | None = None
        self.last_target: str | None = None

    def get_connection_id(self, host_id: str) -> str | None:
        return f"conn-{host_id}" if host_id == self._online_host else None

    def find_online_agent_with_capability(self, capability: str) -> str | None:
        del capability
        return self._online_host

    def register_subscriber(
        self, *, bridge_id: str, rpc_id: str
    ) -> asyncio.Queue[dict[str, Any]]:
        del bridge_id, rpc_id
        return asyncio.Queue()

    def unregister_subscriber(self, *, bridge_id: str, rpc_id: str) -> None:
        del bridge_id, rpc_id

    async def send_to_bridge(
        self, host_id: str, envelope: dict[str, Any]
    ) -> bool:
        self.last_envelope = envelope
        self.last_target = host_id
        return self._send_succeeds

    async def stream_events(
        self,
        *,
        rpc_id: str,
        bridge_id: str | None = None,
        queue: asyncio.Queue[dict[str, Any]] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        del bridge_id, queue
        for raw in self._events:
            event = dict(raw)
            event["correlation_id"] = rpc_id
            yield event


# ---------------------------------------------------------------------------
# Fixture loader.
# ---------------------------------------------------------------------------

_FIXTURE_PATH = (
    Path(__file__).resolve().parents[2] / "fixtures" / "bridge_stream_sample.jsonl"
)


def _load_sample_events() -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with _FIXTURE_PATH.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            events.append(json.loads(line))
    return events


# ---------------------------------------------------------------------------
# OTel exporter fixture.
# ---------------------------------------------------------------------------


@pytest.fixture
def in_memory_spans() -> Iterator[InMemorySpanExporter]:
    """Attach an InMemorySpanExporter to the live tracer provider.

    The OTel global provider is set-once per process; rather than swapping
    it (which would log warnings and lose any existing exporters), we add
    an extra :class:`SimpleSpanProcessor`. The exporter is cleared before
    each test and detached implicitly when the test completes (the
    processor stays attached but the exporter we hand back is freshly
    cleared).
    """
    exporter = InMemorySpanExporter()
    provider = trace.get_tracer_provider()
    sdk_provider: TracerProvider
    if isinstance(provider, TracerProvider):
        sdk_provider = provider
    else:
        sdk_provider = TracerProvider()
        trace.set_tracer_provider(sdk_provider)
    processor = SimpleSpanProcessor(exporter)
    sdk_provider.add_span_processor(processor)
    exporter.clear()
    yield exporter
    # Best-effort flush so any spans straggling in the batch processor
    # are visible to subsequent tests' assertions.
    with contextlib.suppress(Exception):
        sdk_provider.force_flush(timeout_millis=1_000)


# ---------------------------------------------------------------------------
# Tests.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_emits_claude_run_span(
    in_memory_spans: InMemorySpanExporter,
) -> None:
    """A successful run() emits exactly one ``claude.run`` span.

    The span carries the documented attributes (session/bridge/user ids,
    prompt char count, permission mode) and matches the orchestrator's
    OTel naming contract.
    """
    registry = _FakeRegistry(events=_load_sample_events())
    runner = ClaudeCodeRunner(bridge_registry=registry)  # type: ignore[arg-type]

    await runner.run(
        prompt="hello tracing",
        session_id="sess-test",
        bridge_id="mac-1",
        user_id="user-42",
    )

    spans = in_memory_spans.get_finished_spans()
    run_spans = [s for s in spans if s.name == "claude.run"]
    assert len(run_spans) == 1
    span: ReadableSpan = run_spans[0]
    attrs = span.attributes or {}
    assert attrs.get("claude.session_id") == "sess-test"
    assert attrs.get("claude.bridge_id") == "mac-1"
    assert attrs.get("claude.user_id") == "user-42"
    assert attrs.get("claude.prompt_chars") == len("hello tracing")
    assert attrs.get("claude.permission_mode") == "acceptEdits"
    # The runner records the resolved bridge host id as a follow-on attr.
    assert attrs.get("claude.bridge_host_id") == "mac-1"


@pytest.mark.asyncio
async def test_run_emits_dispatch_event_spans_per_event(
    in_memory_spans: InMemorySpanExporter,
) -> None:
    """Every dispatched bridge event becomes a ``claude.dispatch_event`` child.

    The fixture covers the eight Agent-Teams envelope types; we expect
    one dispatch span per event with the matching ``claude.event_type``
    attribute.
    """
    events = _load_sample_events()
    registry = _FakeRegistry(events=events)
    runner = ClaudeCodeRunner(bridge_registry=registry)  # type: ignore[arg-type]

    await runner.run(prompt="ping")

    spans = in_memory_spans.get_finished_spans()
    dispatch_spans = [s for s in spans if s.name == "claude.dispatch_event"]
    # One dispatch span per event in the fixture.
    assert len(dispatch_spans) == len(events)
    span_event_types = sorted(
        str((s.attributes or {}).get("claude.event_type", "")) for s in dispatch_spans
    )
    fixture_event_types = sorted(str(e.get("type", "")) for e in events)
    assert span_event_types == fixture_event_types
    # Every dispatch span carries the bridge host id.
    for s in dispatch_spans:
        attrs = s.attributes or {}
        assert attrs.get("claude.bridge_host_id") == "mac-1"


@pytest.mark.asyncio
async def test_dispatch_event_records_subagent_lifecycle_events(
    in_memory_spans: InMemorySpanExporter,
) -> None:
    """task_started + task_notification dispatch spans carry span events.

    Per T2.1, the runner emits ``subagent.spawned`` on task_started and
    ``subagent.completed`` on task_notification — surfaced as OTel span
    events (not separate spans) so traces stay flat enough to render.
    """
    events = _load_sample_events()
    registry = _FakeRegistry(events=events)
    runner = ClaudeCodeRunner(bridge_registry=registry)  # type: ignore[arg-type]

    await runner.run(prompt="ping")

    spans = in_memory_spans.get_finished_spans()
    dispatch_spans = [s for s in spans if s.name == "claude.dispatch_event"]

    # Find the task_started + task_notification dispatch spans.
    task_started_spans = [
        s
        for s in dispatch_spans
        if (s.attributes or {}).get("claude.event_type") == "event.session.task_started"
    ]
    task_done_spans = [
        s
        for s in dispatch_spans
        if (s.attributes or {}).get("claude.event_type")
        == "event.session.task_notification"
    ]
    assert len(task_started_spans) == 1
    assert len(task_done_spans) == 1

    spawned_event_names = [e.name for e in task_started_spans[0].events]
    assert "subagent.spawned" in spawned_event_names

    completed_event_names = [e.name for e in task_done_spans[0].events]
    assert "subagent.completed" in completed_event_names
