"""Unit tests for LiveActivityPushService — Sprint 2 Live Activity Push.

Tests APNs payload format, headers, throttling, event types, and error handling.
All tests should FAIL until implementation is written (TDD red phase).
"""

import time
from unittest.mock import AsyncMock, patch

import pytest

from app.services.live_activity_push_service import LiveActivityPushService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_PUSH_TOKEN = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6abcd"
BUNDLE_ID = "com.atknatk.rafraf"

VALID_CONTENT_STATE: dict = {
    "status": "implementing",
    "currentStep": "Developer is writing code...",
    "progress": 0.45,
    "completedSteps": 1,
    "totalSteps": 4,
    "estimatedSecondsRemaining": 300,
    "phaseIcon": "hammer.fill",
}


def _make_content_state(**overrides: object) -> dict:
    """Return a valid content-state dict with optional overrides."""
    state = {**VALID_CONTENT_STATE}
    state.update(overrides)
    return state


# ---------------------------------------------------------------------------
# Payload Format Tests
# ---------------------------------------------------------------------------


class TestSendUpdatePayloadFormat:
    """APNs payload structure for Live Activity update events."""

    @pytest.mark.asyncio
    async def test_payload_has_timestamp_integer(self) -> None:
        """payload['aps']['timestamp'] should exist and be an integer."""
        service = LiveActivityPushService()
        mock_send = AsyncMock(return_value=True)

        with patch.object(service, "_send_notification", mock_send):
            await service.send_live_activity_update(
                push_token=SAMPLE_PUSH_TOKEN,
                content_state=_make_content_state(),
            )

        call_args = mock_send.call_args
        payload = call_args.kwargs.get("payload") or call_args[0][1]
        assert "aps" in payload
        assert "timestamp" in payload["aps"]
        assert isinstance(payload["aps"]["timestamp"], int)

    @pytest.mark.asyncio
    async def test_payload_event_is_update(self) -> None:
        """payload['aps']['event'] should be 'update' for update events."""
        service = LiveActivityPushService()
        mock_send = AsyncMock(return_value=True)

        with patch.object(service, "_send_notification", mock_send):
            await service.send_live_activity_update(
                push_token=SAMPLE_PUSH_TOKEN,
                content_state=_make_content_state(),
                event="update",
            )

        call_args = mock_send.call_args
        payload = call_args.kwargs.get("payload") or call_args[0][1]
        assert payload["aps"]["event"] == "update"

    @pytest.mark.asyncio
    async def test_payload_content_state_is_dict(self) -> None:
        """payload['aps']['content-state'] should be a dict."""
        service = LiveActivityPushService()
        mock_send = AsyncMock(return_value=True)

        with patch.object(service, "_send_notification", mock_send):
            await service.send_live_activity_update(
                push_token=SAMPLE_PUSH_TOKEN,
                content_state=_make_content_state(),
            )

        call_args = mock_send.call_args
        payload = call_args.kwargs.get("payload") or call_args[0][1]
        assert isinstance(payload["aps"]["content-state"], dict)

    @pytest.mark.asyncio
    async def test_content_state_has_required_fields(self) -> None:
        """content-state should contain all TaskActivityAttributes.ContentState fields."""
        service = LiveActivityPushService()
        mock_send = AsyncMock(return_value=True)
        cs = _make_content_state()

        with patch.object(service, "_send_notification", mock_send):
            await service.send_live_activity_update(
                push_token=SAMPLE_PUSH_TOKEN,
                content_state=cs,
            )

        call_args = mock_send.call_args
        payload = call_args.kwargs.get("payload") or call_args[0][1]
        content_state = payload["aps"]["content-state"]

        required_fields = {
            "status": str,
            "currentStep": str,
            "progress": float,
            "completedSteps": int,
            "totalSteps": int,
            "phaseIcon": str,
        }
        for field, expected_type in required_fields.items():
            assert field in content_state, f"Missing field: {field}"
            assert isinstance(content_state[field], expected_type), (
                f"Field {field} should be {expected_type.__name__}, "
                f"got {type(content_state[field]).__name__}"
            )

        # estimatedSecondsRemaining can be int or None
        assert "estimatedSecondsRemaining" in content_state
        assert content_state["estimatedSecondsRemaining"] is None or isinstance(
            content_state["estimatedSecondsRemaining"], int
        )

    @pytest.mark.asyncio
    async def test_progress_value_range(self) -> None:
        """progress field should be between 0.0 and 1.0."""
        service = LiveActivityPushService()
        mock_send = AsyncMock(return_value=True)

        with patch.object(service, "_send_notification", mock_send):
            await service.send_live_activity_update(
                push_token=SAMPLE_PUSH_TOKEN,
                content_state=_make_content_state(progress=0.65),
            )

        call_args = mock_send.call_args
        payload = call_args.kwargs.get("payload") or call_args[0][1]
        progress = payload["aps"]["content-state"]["progress"]
        assert 0.0 <= progress <= 1.0


# ---------------------------------------------------------------------------
# Header Tests
# ---------------------------------------------------------------------------


class TestSendUpdateHeaders:
    """APNs headers must follow Live Activity requirements."""

    @pytest.mark.asyncio
    async def test_push_type_header(self) -> None:
        """apns-push-type header should be 'liveactivity'."""
        service = LiveActivityPushService()
        mock_send = AsyncMock(return_value=True)

        with patch.object(service, "_send_notification", mock_send):
            await service.send_live_activity_update(
                push_token=SAMPLE_PUSH_TOKEN,
                content_state=_make_content_state(),
            )

        call_args = mock_send.call_args
        headers = call_args.kwargs.get("headers") or call_args[0][2]
        assert headers["apns-push-type"] == "liveactivity"

    @pytest.mark.asyncio
    async def test_topic_header_format(self) -> None:
        """apns-topic should be '{bundle_id}.push-type.liveactivity'."""
        service = LiveActivityPushService()
        mock_send = AsyncMock(return_value=True)

        with patch.object(service, "_send_notification", mock_send):
            await service.send_live_activity_update(
                push_token=SAMPLE_PUSH_TOKEN,
                content_state=_make_content_state(),
            )

        call_args = mock_send.call_args
        headers = call_args.kwargs.get("headers") or call_args[0][2]
        topic = headers["apns-topic"]
        assert topic.endswith(".push-type.liveactivity")
        # Should start with the bundle ID
        assert topic == f"{BUNDLE_ID}.push-type.liveactivity"

    @pytest.mark.asyncio
    async def test_priority_header(self) -> None:
        """apns-priority should be '10' (high) or '5' (low)."""
        service = LiveActivityPushService()
        mock_send = AsyncMock(return_value=True)

        with patch.object(service, "_send_notification", mock_send):
            await service.send_live_activity_update(
                push_token=SAMPLE_PUSH_TOKEN,
                content_state=_make_content_state(),
            )

        call_args = mock_send.call_args
        headers = call_args.kwargs.get("headers") or call_args[0][2]
        assert headers["apns-priority"] in ("10", "5")


# ---------------------------------------------------------------------------
# End Event Tests
# ---------------------------------------------------------------------------


class TestSendEndEvent:
    """APNs payload for Live Activity end (dismissal) event."""

    @pytest.mark.asyncio
    async def test_end_event_value(self) -> None:
        """payload['aps']['event'] should be 'end'."""
        service = LiveActivityPushService()
        mock_send = AsyncMock(return_value=True)

        with patch.object(service, "_send_notification", mock_send):
            await service.send_live_activity_end(
                push_token=SAMPLE_PUSH_TOKEN,
                content_state=_make_content_state(status="completed", progress=1.0),
            )

        call_args = mock_send.call_args
        payload = call_args.kwargs.get("payload") or call_args[0][1]
        assert payload["aps"]["event"] == "end"

    @pytest.mark.asyncio
    async def test_dismissal_date_present(self) -> None:
        """End event should include a dismissal-date field."""
        service = LiveActivityPushService()
        mock_send = AsyncMock(return_value=True)

        with patch.object(service, "_send_notification", mock_send):
            await service.send_live_activity_end(
                push_token=SAMPLE_PUSH_TOKEN,
                content_state=_make_content_state(status="completed", progress=1.0),
                dismissal_hours=4,
            )

        call_args = mock_send.call_args
        payload = call_args.kwargs.get("payload") or call_args[0][1]
        assert "dismissal-date" in payload["aps"]
        assert isinstance(payload["aps"]["dismissal-date"], int)
        # dismissal-date should be in the future
        assert payload["aps"]["dismissal-date"] > int(time.time())


# ---------------------------------------------------------------------------
# Throttle Tests
# ---------------------------------------------------------------------------


class TestThrottleRapidUpdates:
    """Rate limiting: max 1 push per 30 seconds per token."""

    @pytest.mark.asyncio
    async def test_rapid_updates_throttled(self) -> None:
        """Sending 5 rapid updates should result in only 1 actual push."""
        service = LiveActivityPushService()
        mock_send = AsyncMock(return_value=True)

        with patch.object(service, "_send_notification", mock_send):
            for _ in range(5):
                await service.send_live_activity_update(
                    push_token=SAMPLE_PUSH_TOKEN,
                    content_state=_make_content_state(),
                )

        # Only the first call should go through
        assert mock_send.call_count == 1

    @pytest.mark.asyncio
    async def test_throttle_expires_allows_next_push(self) -> None:
        """After throttle window passes, next push should be sent."""
        service = LiveActivityPushService()
        mock_send = AsyncMock(return_value=True)

        with patch.object(service, "_send_notification", mock_send):
            # First push goes through
            await service.send_live_activity_update(
                push_token=SAMPLE_PUSH_TOKEN,
                content_state=_make_content_state(progress=0.2),
            )
            assert mock_send.call_count == 1

            # Simulate time passing beyond throttle window (30s)
            with patch("time.time", return_value=time.time() + 31):
                await service.send_live_activity_update(
                    push_token=SAMPLE_PUSH_TOKEN,
                    content_state=_make_content_state(progress=0.5),
                )
            assert mock_send.call_count == 2


# ---------------------------------------------------------------------------
# Stale Date Tests
# ---------------------------------------------------------------------------


class TestStaleDate:
    """stale-date should be at top-level of payload (not inside aps)."""

    @pytest.mark.asyncio
    async def test_stale_date_at_top_level(self) -> None:
        """stale-date should be a top-level payload key, not inside aps."""
        service = LiveActivityPushService()
        mock_send = AsyncMock(return_value=True)

        with patch.object(service, "_send_notification", mock_send):
            await service.send_live_activity_update(
                push_token=SAMPLE_PUSH_TOKEN,
                content_state=_make_content_state(),
                stale_minutes=15,
            )

        call_args = mock_send.call_args
        payload = call_args.kwargs.get("payload") or call_args[0][1]

        # stale-date should NOT be inside aps
        assert "stale-date" not in payload.get("aps", {})
        # stale-date SHOULD be at top level
        assert "stale-date" in payload

    @pytest.mark.asyncio
    async def test_stale_date_in_future(self) -> None:
        """stale-date should be greater than current timestamp."""
        service = LiveActivityPushService()
        mock_send = AsyncMock(return_value=True)

        with patch.object(service, "_send_notification", mock_send):
            await service.send_live_activity_update(
                push_token=SAMPLE_PUSH_TOKEN,
                content_state=_make_content_state(),
                stale_minutes=15,
            )

        call_args = mock_send.call_args
        payload = call_args.kwargs.get("payload") or call_args[0][1]
        assert payload["stale-date"] > int(time.time())


# ---------------------------------------------------------------------------
# Timestamp Monotonic Tests
# ---------------------------------------------------------------------------


class TestTimestampMonotonic:
    """Each update's timestamp must be strictly increasing."""

    @pytest.mark.asyncio
    async def test_second_timestamp_greater_than_first(self) -> None:
        """Two successive updates should have monotonically increasing timestamps."""
        service = LiveActivityPushService()
        mock_send = AsyncMock(return_value=True)
        timestamps: list[int] = []

        def capture_payload(*args: object, **kwargs: object) -> bool:
            payload = kwargs.get("payload") or args[1]
            timestamps.append(payload["aps"]["timestamp"])
            return True

        mock_send.side_effect = capture_payload

        with patch.object(service, "_send_notification", mock_send):
            await service.send_live_activity_update(
                push_token=SAMPLE_PUSH_TOKEN,
                content_state=_make_content_state(progress=0.3),
            )

            # Bypass throttle for second call
            with patch("time.time", return_value=time.time() + 31):
                await service.send_live_activity_update(
                    push_token=SAMPLE_PUSH_TOKEN,
                    content_state=_make_content_state(progress=0.6),
                )

        assert len(timestamps) == 2
        assert timestamps[1] > timestamps[0]


# ---------------------------------------------------------------------------
# Invalid Token Handling Tests
# ---------------------------------------------------------------------------


class TestInvalidTokenHandling:
    """Service should handle APNs 410 Gone (invalid token) gracefully."""

    @pytest.mark.asyncio
    async def test_410_marks_token_invalid(self) -> None:
        """When APNs returns 410 Gone, the token should be marked invalid."""
        service = LiveActivityPushService()

        # Simulate 410 Gone response
        mock_send = AsyncMock(side_effect=Exception("410 Gone"))

        with patch.object(service, "_send_notification", mock_send):
            result = await service.send_live_activity_update(
                push_token=SAMPLE_PUSH_TOKEN,
                content_state=_make_content_state(),
            )

        # Should return False indicating failure
        assert result is False
        # Token should be marked as invalid internally
        assert service._should_skip_token(SAMPLE_PUSH_TOKEN) is True

    @pytest.mark.asyncio
    async def test_subsequent_push_skipped_for_invalid_token(self) -> None:
        """After 410, subsequent pushes to the same token should be skipped."""
        service = LiveActivityPushService()
        mock_send = AsyncMock(side_effect=Exception("410 Gone"))

        with patch.object(service, "_send_notification", mock_send):
            # First call — triggers 410
            await service.send_live_activity_update(
                push_token=SAMPLE_PUSH_TOKEN,
                content_state=_make_content_state(),
            )

        # Reset mock — next call should NOT reach _send_notification
        mock_send_2 = AsyncMock(return_value=True)
        with (
            patch.object(service, "_send_notification", mock_send_2),
            patch("time.time", return_value=time.time() + 31),
        ):
            result = await service.send_live_activity_update(
                push_token=SAMPLE_PUSH_TOKEN,
                content_state=_make_content_state(),
            )

        assert result is False
        mock_send_2.assert_not_called()


# ---------------------------------------------------------------------------
# Content State Matches iOS Attributes Tests
# ---------------------------------------------------------------------------


class TestContentStateMatchesAttributes:
    """ContentState fields must match iOS TaskActivityAttributes.ContentState struct."""

    @pytest.mark.asyncio
    async def test_all_required_fields_present(self) -> None:
        """All ContentState fields defined in iOS struct must be present."""
        service = LiveActivityPushService()
        mock_send = AsyncMock(return_value=True)

        with patch.object(service, "_send_notification", mock_send):
            await service.send_live_activity_update(
                push_token=SAMPLE_PUSH_TOKEN,
                content_state=_make_content_state(),
            )

        call_args = mock_send.call_args
        payload = call_args.kwargs.get("payload") or call_args[0][1]
        cs = payload["aps"]["content-state"]

        expected_fields = [
            "status",
            "currentStep",
            "progress",
            "completedSteps",
            "totalSteps",
            "estimatedSecondsRemaining",
            "phaseIcon",
        ]
        for field in expected_fields:
            assert field in cs, f"Missing iOS ContentState field: {field}"

    @pytest.mark.asyncio
    async def test_field_types_correct(self) -> None:
        """Field types should match Swift Codable expectations."""
        service = LiveActivityPushService()
        mock_send = AsyncMock(return_value=True)

        with patch.object(service, "_send_notification", mock_send):
            await service.send_live_activity_update(
                push_token=SAMPLE_PUSH_TOKEN,
                content_state=_make_content_state(),
            )

        call_args = mock_send.call_args
        payload = call_args.kwargs.get("payload") or call_args[0][1]
        cs = payload["aps"]["content-state"]

        assert isinstance(cs["status"], str)
        assert isinstance(cs["currentStep"], str)
        assert isinstance(cs["progress"], float)
        assert isinstance(cs["completedSteps"], int)
        assert isinstance(cs["totalSteps"], int)
        assert isinstance(cs["phaseIcon"], str)
        # estimatedSecondsRemaining is Optional<Int> in Swift
        assert cs["estimatedSecondsRemaining"] is None or isinstance(
            cs["estimatedSecondsRemaining"], int
        )
