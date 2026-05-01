"""Unit tests for agent_ws.py module-level handlers.

Focused on the T1.2 ``event.usage.report`` broadcast path — we exercise it
in isolation by patching the ``ios_manager`` and ``claude_stream_manager``
singletons so no real WebSocket / DB round-trip is required.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.routes import agent_ws as agent_ws_module
from app.schemas.messages import MessageType


@pytest.fixture
def fake_ios_manager(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Patch the iOS-side ConnectionManager singleton with a mock."""
    fake = MagicMock()
    fake.send_to_user = AsyncMock(return_value=2)
    fake.get_active_user_ids = MagicMock(return_value={"user-A", "user-B"})
    monkeypatch.setattr(
        "app.api.routes.websocket.manager",
        fake,
        raising=False,
    )
    return fake


@pytest.fixture
def fake_csm(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Replace get_claude_stream_manager() with a mock that records forwards."""
    fake = MagicMock()
    fake.forward_usage_report = AsyncMock(return_value=2)
    monkeypatch.setattr(
        agent_ws_module,
        "get_claude_stream_manager",
        lambda: fake,
    )
    return fake


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_ios_manager")
async def test_handle_usage_report_broadcasts_to_every_active_user(
    fake_csm: MagicMock,
) -> None:
    """Each active iOS user MUST receive a forward_usage_report call."""
    raw = {
        "type": "event.usage.report",
        "payload": {
            "five_hour_pct": 73,
            "seven_day_pct": 41,
            "five_hour_resets_at": 1735689600,
            "seven_day_resets_at": 1736294400,
            "reported_at": 1735680000,
        },
    }
    await agent_ws_module._handle_usage_report(raw)

    # 2 active users → 2 forwarder invocations.
    assert fake_csm.forward_usage_report.await_count == 2
    forwarded_users = {
        call.kwargs["user_id"] for call in fake_csm.forward_usage_report.await_args_list
    }
    assert forwarded_users == {"user-A", "user-B"}

    # The payload fields propagate verbatim.
    sample = fake_csm.forward_usage_report.await_args_list[0]
    assert sample.kwargs["five_hour_pct"] == 73
    assert sample.kwargs["seven_day_pct"] == 41
    assert sample.kwargs["five_hour_resets_at"] == 1735689600
    assert sample.kwargs["seven_day_resets_at"] == 1736294400
    assert sample.kwargs["reported_at"] == 1735680000


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_ios_manager")
async def test_handle_usage_report_falls_back_to_content_key(
    fake_csm: MagicMock,
) -> None:
    """Legacy bridges that put fields under ``content`` must still work."""
    raw = {
        "type": "event.usage.report",
        "content": {
            "five_hour_pct": 5,
            "seven_day_pct": 2,
            "five_hour_resets_at": 1735689600,
            "seven_day_resets_at": 1736294400,
            "reported_at": 1735680000,
        },
    }
    await agent_ws_module._handle_usage_report(raw)
    assert fake_csm.forward_usage_report.await_count == 2  # one per active user


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_ios_manager")
async def test_handle_usage_report_ignores_missing_payload(
    fake_csm: MagicMock,
) -> None:
    """Envelopes without payload/content MUST NOT raise — just log + skip."""
    await agent_ws_module._handle_usage_report({"type": "event.usage.report"})
    fake_csm.forward_usage_report.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_ios_manager")
async def test_handle_usage_report_ignores_invalid_payload_types(
    fake_csm: MagicMock,
) -> None:
    """Coercion errors MUST be swallowed (warn + skip), not propagated."""
    raw = {
        "type": "event.usage.report",
        "payload": {
            "five_hour_pct": "not-a-number",  # broken
            "seven_day_pct": 0,
            "five_hour_resets_at": 0,
            "seven_day_resets_at": 0,
            "reported_at": 0,
        },
    }
    await agent_ws_module._handle_usage_report(raw)
    fake_csm.forward_usage_report.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_usage_report_no_active_users_is_noop(
    fake_ios_manager: MagicMock,
    fake_csm: MagicMock,
) -> None:
    """No connected iOS users → no forwarder calls (early return)."""
    fake_ios_manager.get_active_user_ids.return_value = set()
    raw = {
        "type": "event.usage.report",
        "payload": {
            "five_hour_pct": 10,
            "seven_day_pct": 5,
            "five_hour_resets_at": 0,
            "seven_day_resets_at": 0,
            "reported_at": 0,
        },
    }
    await agent_ws_module._handle_usage_report(raw)
    fake_csm.forward_usage_report.assert_not_awaited()


def test_usage_report_message_type_is_registered() -> None:
    """Sanity: USAGE_REPORT enum + value match the bridge wire format suffix."""
    assert MessageType.USAGE_REPORT.value == "usage.report"
