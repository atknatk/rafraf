"""T2.4 — Anthropic 429 fallback rate-limit tests.

Covers the direct-API path (``OrchestratorAgent._call_claude_api``):
    * On ``RateLimitError`` the agent calls the wired forwarder with a
      ``RateLimitInfoPayload``-shaped dict, derives ``resets_at`` from the
      ``Retry-After`` header (or a 5-hour default when missing), and bumps
      ``claude_rate_limit_hits_total{bridge_id="api", rate_limit_type="five_hour"}``.
    * Forwarder failures are swallowed so the retry loop keeps progressing.
    * ``user_id=None`` skips the forwarder but still bumps the counter.
    * ``_parse_retry_after_seconds`` handles missing headers, integer-seconds,
      HTTP-date forms, garbage, and negative values.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import anthropic
import httpx
import pytest

from app.core.metrics import claude_rate_limit_hits_total
from app.orchestrator.agent import (
    ClaudeAPIError,
    OrchestratorAgent,
    _parse_retry_after_seconds,
)
from app.orchestrator.tool_registry import ToolRegistry
from app.schemas.orchestrator import OrchestratorRequest

# ---------------------------------------------------------------------------
# Helpers.
# ---------------------------------------------------------------------------


def _make_rate_limit_error(retry_after: str | None = "120") -> anthropic.RateLimitError:
    """Build a real ``anthropic.RateLimitError`` with a synthetic httpx Response.

    Mirrors what the SDK constructs in production so attribute access
    (``exc.response.headers``) goes through the same code path the agent
    relies on.
    """
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    headers = httpx.Headers()
    if retry_after is not None:
        headers["retry-after"] = retry_after
    response = httpx.Response(
        429,
        request=request,
        headers=headers,
        json={"error": {"type": "rate_limit_error", "message": "rate limited"}},
    )
    return anthropic.RateLimitError(
        "rate limited",
        response=response,
        body=None,
    )


def _make_text_response(text: str = "ok") -> MagicMock:
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = text
    usage = MagicMock()
    usage.input_tokens = 10
    usage.output_tokens = 5
    response = MagicMock()
    response.content = [text_block]
    response.usage = usage
    return response


def _counter_value(*, bridge_id: str, rate_limit_type: str) -> float:
    """Read the current value of the labelled counter for assertion deltas."""
    sample = claude_rate_limit_hits_total.labels(
        bridge_id=bridge_id,
        rate_limit_type=rate_limit_type,
    )
    return float(sample._value.get())  # noqa: SLF001 — Counter API exposes private attr


# ---------------------------------------------------------------------------
# _parse_retry_after_seconds — pure unit tests (no SDK / mocks).
# ---------------------------------------------------------------------------


class TestParseRetryAfter:
    """T2.4 — header parsing should accept seconds, HTTP-dates, and reject junk."""

    def test_returns_integer_seconds(self) -> None:
        exc = _make_rate_limit_error(retry_after="42")
        assert _parse_retry_after_seconds(exc) == 42

    def test_negative_seconds_clamped_to_zero(self) -> None:
        exc = _make_rate_limit_error(retry_after="-5")
        assert _parse_retry_after_seconds(exc) == 0

    def test_missing_header_returns_none(self) -> None:
        exc = _make_rate_limit_error(retry_after=None)
        assert _parse_retry_after_seconds(exc) is None

    def test_garbage_returns_none(self) -> None:
        exc = _make_rate_limit_error(retry_after="not-a-number-or-date")
        assert _parse_retry_after_seconds(exc) is None

    def test_empty_string_returns_none(self) -> None:
        exc = _make_rate_limit_error(retry_after="   ")
        assert _parse_retry_after_seconds(exc) is None

    def test_http_date_returns_seconds_until(self) -> None:
        # Construct a date well in the future. Result must be > 0.
        future = datetime.now(tz=UTC) + timedelta(seconds=300)
        exc = _make_rate_limit_error(retry_after=format_datetime(future, usegmt=True))
        seconds = _parse_retry_after_seconds(exc)
        assert seconds is not None
        assert 290 <= seconds <= 305

    def test_response_without_headers_returns_none(self) -> None:
        # Synthesise a malformed exc — exercise the defensive branch.
        exc = _make_rate_limit_error(retry_after="42")
        exc.response = cast(httpx.Response, object())  # strip headers attr
        assert _parse_retry_after_seconds(exc) is None


# ---------------------------------------------------------------------------
# Agent integration — _call_claude_api on RateLimitError.
# ---------------------------------------------------------------------------


@patch("app.orchestrator.agent.get_settings")
@patch("app.orchestrator.agent.anthropic.AsyncAnthropic")
async def test_rate_limit_invokes_forwarder_with_payload(
    mock_anthropic_cls: MagicMock,
    mock_settings: MagicMock,
) -> None:
    """T2.4 — first 429 calls forwarder with retry-after-derived resets_at."""
    mock_settings.return_value.anthropic_api_key = "test-key"
    mock_settings.return_value.claude_default_model = "claude-opus-4-7"

    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create = AsyncMock(
        side_effect=[
            _make_rate_limit_error(retry_after="60"),
            _make_text_response("Done after retry"),
        ]
    )

    forwarder = AsyncMock()
    agent = OrchestratorAgent(ToolRegistry(), rate_limit_forwarder=forwarder)
    request = OrchestratorRequest(
        session_id="sess_x",
        user_id="user_x",
        message="hi",
    )

    # Patch sleep so the test doesn't really wait 1s.
    with patch("app.orchestrator.agent.asyncio.sleep", new=AsyncMock()):
        response = await agent.process_message(request)

    assert response.response_text == "Done after retry"
    forwarder.assert_awaited_once()
    received_user_id, received_payload = forwarder.await_args.args
    assert received_user_id == "user_x"
    assert received_payload["status"] == "exceeded"
    assert received_payload["rate_limit_type"] == "five_hour"
    assert received_payload["session_id"] == "sess_x"
    # resets_at should be ~now + 60 seconds.
    now = int(time.time())
    assert now + 55 <= cast(int, received_payload["resets_at"]) <= now + 65
    assert received_payload["overage_status"] == "unknown"
    assert received_payload["is_using_overage"] is False


@patch("app.orchestrator.agent.get_settings")
@patch("app.orchestrator.agent.anthropic.AsyncAnthropic")
async def test_rate_limit_increments_counter_with_api_sentinel(
    mock_anthropic_cls: MagicMock,
    mock_settings: MagicMock,
) -> None:
    """T2.4 — counter labels MUST be (bridge_id="api", rate_limit_type="five_hour")."""
    mock_settings.return_value.anthropic_api_key = "test-key"
    mock_settings.return_value.claude_default_model = "claude-opus-4-7"

    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create = AsyncMock(
        side_effect=[
            _make_rate_limit_error(retry_after="30"),
            _make_text_response("ok"),
        ]
    )

    before = _counter_value(bridge_id="api", rate_limit_type="five_hour")

    agent = OrchestratorAgent(ToolRegistry())
    request = OrchestratorRequest(
        session_id="sess_y",
        user_id="user_y",
        message="hi",
    )
    with patch("app.orchestrator.agent.asyncio.sleep", new=AsyncMock()):
        await agent.process_message(request)

    after = _counter_value(bridge_id="api", rate_limit_type="five_hour")
    assert after - before == 1.0


@patch("app.orchestrator.agent.get_settings")
@patch("app.orchestrator.agent.anthropic.AsyncAnthropic")
async def test_rate_limit_default_window_when_header_missing(
    mock_anthropic_cls: MagicMock,
    mock_settings: MagicMock,
) -> None:
    """No ``Retry-After`` header → agent synthesises a 5-hour window."""
    mock_settings.return_value.anthropic_api_key = "test-key"
    mock_settings.return_value.claude_default_model = "claude-opus-4-7"

    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create = AsyncMock(
        side_effect=[
            _make_rate_limit_error(retry_after=None),
            _make_text_response("ok"),
        ]
    )

    forwarder = AsyncMock()
    agent = OrchestratorAgent(ToolRegistry(), rate_limit_forwarder=forwarder)
    request = OrchestratorRequest(
        session_id="sess_z",
        user_id="user_z",
        message="hi",
    )
    with patch("app.orchestrator.agent.asyncio.sleep", new=AsyncMock()):
        await agent.process_message(request)

    forwarder.assert_awaited_once()
    _, payload = forwarder.await_args.args
    now = int(time.time())
    expected_min = now + (5 * 60 * 60) - 5
    expected_max = now + (5 * 60 * 60) + 5
    assert expected_min <= cast(int, payload["resets_at"]) <= expected_max


@patch("app.orchestrator.agent.get_settings")
@patch("app.orchestrator.agent.anthropic.AsyncAnthropic")
async def test_forwarder_exception_swallowed(
    mock_anthropic_cls: MagicMock,
    mock_settings: MagicMock,
) -> None:
    """A broken forwarder MUST not break the agent's retry loop."""
    mock_settings.return_value.anthropic_api_key = "test-key"
    mock_settings.return_value.claude_default_model = "claude-opus-4-7"

    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create = AsyncMock(
        side_effect=[
            _make_rate_limit_error(retry_after="10"),
            _make_text_response("recovered"),
        ]
    )

    async def _boom(_uid: str, _payload: dict[str, object]) -> None:
        raise RuntimeError("ws disconnected")

    agent = OrchestratorAgent(
        ToolRegistry(),
        rate_limit_forwarder=cast(
            "Awaitable[None]",
            _boom,  # type: ignore[arg-type]
        ),
    )
    request = OrchestratorRequest(
        session_id="sess_a",
        user_id="user_a",
        message="hi",
    )
    with patch("app.orchestrator.agent.asyncio.sleep", new=AsyncMock()):
        response = await agent.process_message(request)
    assert response.response_text == "recovered"


@patch("app.orchestrator.agent.get_settings")
@patch("app.orchestrator.agent.anthropic.AsyncAnthropic")
async def test_forwarder_skipped_when_user_id_missing(
    mock_anthropic_cls: MagicMock,
    mock_settings: MagicMock,
) -> None:
    """No user_id → forwarder is NOT called, but counter still increments."""
    mock_settings.return_value.anthropic_api_key = "test-key"
    mock_settings.return_value.claude_default_model = "claude-opus-4-7"

    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client

    forwarder = AsyncMock()
    agent = OrchestratorAgent(ToolRegistry(), rate_limit_forwarder=forwarder)

    before = _counter_value(bridge_id="api", rate_limit_type="five_hour")

    # Direct call to _call_claude_api with user_id=None.
    mock_client.messages.create = AsyncMock(
        side_effect=[
            _make_rate_limit_error(retry_after="30"),
            _make_text_response("ok"),
        ]
    )
    with patch("app.orchestrator.agent.asyncio.sleep", new=AsyncMock()):
        await agent._call_claude_api(  # noqa: SLF001 — covering private path
            model="claude-opus-4-7",
            system="sys",
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
            user_id=None,
            session_id=None,
        )

    after = _counter_value(bridge_id="api", rate_limit_type="five_hour")
    assert after - before == 1.0
    forwarder.assert_not_awaited()


@patch("app.orchestrator.agent.get_settings")
@patch("app.orchestrator.agent.anthropic.AsyncAnthropic")
async def test_rate_limit_terminal_raises_claude_api_error(
    mock_anthropic_cls: MagicMock,
    mock_settings: MagicMock,
) -> None:
    """All retries 429 → final ClaudeAPIError; counter increments per attempt."""
    mock_settings.return_value.anthropic_api_key = "test-key"
    mock_settings.return_value.claude_default_model = "claude-opus-4-7"

    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create = AsyncMock(
        side_effect=[
            _make_rate_limit_error(retry_after="5"),
            _make_rate_limit_error(retry_after="5"),
            _make_rate_limit_error(retry_after="5"),
        ]
    )

    before = _counter_value(bridge_id="api", rate_limit_type="five_hour")

    agent = OrchestratorAgent(ToolRegistry())
    request = OrchestratorRequest(
        session_id="sess_b",
        user_id="user_b",
        message="hi",
    )
    with (
        patch("app.orchestrator.agent.asyncio.sleep", new=AsyncMock()),
        pytest.raises(ClaudeAPIError),
    ):
        await agent.process_message(request)

    after = _counter_value(bridge_id="api", rate_limit_type="five_hour")
    # Each of the 3 retry attempts MUST bump the counter.
    assert after - before == 3.0


# ---------------------------------------------------------------------------
# set_rate_limit_forwarder — late binding contract.
# ---------------------------------------------------------------------------


def test_set_rate_limit_forwarder_replaces_wired_callback() -> None:
    """Late-binding swaps the forwarder; bool readiness held in the attribute."""
    agent = OrchestratorAgent(ToolRegistry())
    assert agent._rate_limit_forwarder is None  # noqa: SLF001

    forwarder = AsyncMock()
    agent.set_rate_limit_forwarder(forwarder)
    assert agent._rate_limit_forwarder is forwarder  # noqa: SLF001

    agent.set_rate_limit_forwarder(None)
    assert agent._rate_limit_forwarder is None  # noqa: SLF001
