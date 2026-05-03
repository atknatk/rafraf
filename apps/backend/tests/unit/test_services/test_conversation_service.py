"""Unit tests for ConversationService.

Covers the two recently-discovered safety/correctness gaps:

1. ``Message.content`` had no size cap on either the model or the service. A
   50MB assistant response would persist and later crash older iOS devices
   when JSONDecoder tried to load the entire string. ``save_message`` must
   now cap content at ``MAX_MESSAGE_CONTENT_BYTES`` (1MB UTF-8):
     * USER messages exceeding the cap raise ``MessageTooLargeError`` (413).
     * ASSISTANT messages exceeding the cap are truncated with a sentinel
       and a ``assistant_message_truncated`` warning is logged.

2. ``get_messages_since`` silently truncated at ``LIMIT 200`` and always
   returned ``has_more=False`` / ``next_cursor=None``. Any user offline for
   more than 200 missed messages would see *silent* data loss with no UI
   indicator. The query must over-fetch by 1, set ``has_more`` accordingly,
   trim the extra row, and emit a ``next_cursor`` so iOS can keep paging.

These tests are written TDD-first — they fail against the current
implementation. The developer agent will then make them pass.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import MessageTooLargeError
from app.models.message import Message
from app.services.conversation_service import (
    EXPORT_MESSAGE_LIMIT,
    MAX_MESSAGE_CONTENT_BYTES,
    ConversationService,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session() -> AsyncMock:
    """Build a minimal AsyncSession-like mock.

    ``add`` is sync on a real AsyncSession, ``flush`` is async.
    """
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    return session


def _make_message_row(
    *,
    role: str = "user",
    content: str = "hi",
    created_at: datetime | None = None,
    session_id: str = "sess-1",
    user_id: str = "user-1",
) -> Message:
    """Build a Message-shaped mock for query result rows.

    We use MagicMock(spec=Message) so attribute access mirrors the real model
    without requiring a database round-trip.
    """
    msg = MagicMock(spec=Message)
    msg.id = uuid.uuid4()
    msg.session_id = session_id
    msg.user_id = user_id
    msg.project_id = None
    msg.agent_id = None
    msg.role = role
    msg.content = content
    msg.model_used = None
    msg.tokens_used = None
    msg.created_at = created_at or datetime.now(tz=UTC)
    msg.rating = None
    msg.rating_note = None
    msg.rated_at = None
    return msg


def _wire_execute_returning(session: AsyncMock, rows: list[Message]) -> None:
    """Wire session.execute(...) -> .scalars() -> iterable of rows.

    Mirrors the real SQLAlchemy chain used by ConversationService.
    """
    mock_scalars = MagicMock()
    mock_scalars.__iter__ = lambda _self: iter(rows)
    mock_scalars.all.return_value = rows
    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars
    session.execute = AsyncMock(return_value=mock_result)


# ---------------------------------------------------------------------------
# save_message — content size cap
# ---------------------------------------------------------------------------


class TestSaveMessageSizeCap:
    """``save_message`` must enforce ``MAX_MESSAGE_CONTENT_BYTES`` per role."""

    async def test_save_message_under_cap_persists_intact(self) -> None:
        """A 999KB body (under the 1MB cap) is stored byte-for-byte."""
        session = _make_session()
        service = ConversationService(session)

        # 999_000 ASCII bytes — comfortably under the 1MB cap.
        content = "a" * 999_000
        assert len(content.encode("utf-8")) < MAX_MESSAGE_CONTENT_BYTES

        msg = await service.save_message(
            session_id="sess-1",
            user_id="user-1",
            role="user",
            content=content,
        )

        # Stored content is unchanged.
        assert msg.content == content
        # Persisted via session.add + flush.
        session.add.assert_called_once()
        session.flush.assert_awaited_once()

    async def test_save_message_user_too_large_raises_413(self) -> None:
        """User-role payload above the cap raises MessageTooLargeError (413)."""
        session = _make_session()
        service = ConversationService(session)

        # 1 byte over the cap.
        oversize = "x" * (MAX_MESSAGE_CONTENT_BYTES + 1)

        with pytest.raises(MessageTooLargeError) as excinfo:
            await service.save_message(
                session_id="sess-1",
                user_id="user-1",
                role="user",
                content=oversize,
            )

        # 413 maps from the AppError base.
        assert excinfo.value.status_code == 413
        # Nothing should have been written to the DB on the rejection path.
        session.add.assert_not_called()
        session.flush.assert_not_awaited()

    async def test_save_message_user_too_large_multibyte_raises(self) -> None:
        """The cap is in BYTES (UTF-8), not characters.

        A string whose char count is below the cap but whose UTF-8 byte
        length is above it must still be rejected.
        """
        session = _make_session()
        service = ConversationService(session)

        # Each "ş" is 2 bytes in UTF-8; produce >1MB bytes from <1M chars.
        char_count = (MAX_MESSAGE_CONTENT_BYTES // 2) + 50
        oversize = "ş" * char_count
        assert len(oversize) < MAX_MESSAGE_CONTENT_BYTES
        assert len(oversize.encode("utf-8")) > MAX_MESSAGE_CONTENT_BYTES

        with pytest.raises(MessageTooLargeError):
            await service.save_message(
                session_id="sess-1",
                user_id="user-1",
                role="user",
                content=oversize,
            )

    async def test_save_message_assistant_too_large_truncates(self) -> None:
        """Assistant response above the cap is truncated with a sentinel."""
        session = _make_session()
        service = ConversationService(session)

        # 2x the cap to force truncation.
        original = "y" * (MAX_MESSAGE_CONTENT_BYTES * 2)
        original_bytes = len(original.encode("utf-8"))

        msg = await service.save_message(
            session_id="sess-42",
            user_id="user-1",
            role="assistant",
            content=original,
        )

        stored = msg.content
        stored_bytes = len(stored.encode("utf-8"))

        # The stored content is shorter than the original.
        assert stored_bytes < original_bytes

        # It stays under the cap (allowing room for the sentinel suffix).
        # Spec: truncate to (MAX - 200) and append sentinel.
        # Allow generous headroom (300B) for sentinel formatting variance.
        assert stored_bytes <= MAX_MESSAGE_CONTENT_BYTES + 300

        # The sentinel must be present so clients can render an indicator.
        assert "truncated" in stored.lower()
        # The original byte size should be reported in the sentinel for
        # observability — operators reading the stored row should see how
        # large the original was.
        assert str(original_bytes) in stored

        # Persisted (assistant truncation does NOT block the write).
        session.add.assert_called_once()
        session.flush.assert_awaited_once()

    async def test_save_message_assistant_at_cap_persists_intact(self) -> None:
        """Assistant response exactly at the cap is NOT truncated."""
        session = _make_session()
        service = ConversationService(session)

        content = "z" * MAX_MESSAGE_CONTENT_BYTES
        msg = await service.save_message(
            session_id="sess-1",
            user_id="user-1",
            role="assistant",
            content=content,
        )

        # Boundary: exactly at the cap should not trigger truncation.
        assert msg.content == content
        assert "truncated" not in msg.content.lower()


# ---------------------------------------------------------------------------
# get_messages_since — pagination + has_more cursor
# ---------------------------------------------------------------------------


class TestGetMessagesSincePagination:
    """``get_messages_since`` must surface pagination so iOS can keep paging."""

    async def test_get_messages_since_under_limit_has_more_false(self) -> None:
        """N=50 rows under limit=200 → has_more=False, next cursor None."""
        session = _make_session()
        service = ConversationService(session)

        base = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
        rows = [
            _make_message_row(
                content=f"m{i}",
                created_at=base + timedelta(seconds=i),
            )
            for i in range(50)
        ]
        # Service over-fetches by 1; under-limit returns exactly N rows.
        _wire_execute_returning(session, rows)

        resp = await service.get_messages_since(
            since="2026-05-01T11:59:00+00:00",
        )

        assert len(resp.messages) == 50
        assert resp.has_more is False
        # Spec: when there's no further page, next cursor is None. The schema
        # field name is `next_cursor`; future iterations may also expose
        # `next_since` as an alias — accept either, but require absence here.
        cursor = _read_next_cursor(resp)
        assert cursor is None

    async def test_get_messages_since_at_limit_plus_one_has_more_true(
        self,
    ) -> None:
        """N=201 rows → has_more=True, returned trimmed to 200, cursor set."""
        session = _make_session()
        service = ConversationService(session)

        base = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
        # 201 rows: service should over-fetch (limit+1) and trim to 200.
        rows = [
            _make_message_row(
                content=f"m{i}",
                created_at=base + timedelta(seconds=i),
            )
            for i in range(201)
        ]
        _wire_execute_returning(session, rows)

        resp = await service.get_messages_since(
            since="2026-05-01T11:59:00+00:00",
            limit=200,
        )

        # Trimmed to the requested limit.
        assert len(resp.messages) == 200
        assert resp.has_more is True

        # Cursor is the created_at of the last delivered row (ISO 8601).
        cursor = _read_next_cursor(resp)
        assert cursor is not None
        # Must match the last delivered message's timestamp so the next
        # call passes ``since=cursor`` and gets row #201 onward.
        last_delivered = resp.messages[-1]
        assert cursor == last_delivered.created_at

    async def test_get_messages_since_pagination_round_trip(self) -> None:
        """Two sequential calls walk the full set without dropping rows."""
        service_session = _make_session()
        service = ConversationService(service_session)

        base = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
        all_rows = [
            _make_message_row(
                content=f"m{i}",
                created_at=base + timedelta(seconds=i),
            )
            for i in range(250)
        ]

        # ---- Call 1: rows 0..199 (limit=200), has_more=True ----
        # Service over-fetches by 1, so feed it 201 rows.
        _wire_execute_returning(service_session, all_rows[:201])
        page1 = await service.get_messages_since(
            since="2026-05-01T11:59:00+00:00",
            limit=200,
        )

        assert len(page1.messages) == 200
        assert page1.has_more is True
        cursor = _read_next_cursor(page1)
        assert cursor is not None

        # ---- Call 2: pass the cursor → rows 200..249 (50 rows), has_more=False ----
        # The remaining 50 rows fit under the limit, so no over-fetch trim.
        _wire_execute_returning(service_session, all_rows[200:250])
        page2 = await service.get_messages_since(
            since=cursor,
            limit=200,
        )

        assert len(page2.messages) == 50
        assert page2.has_more is False
        assert _read_next_cursor(page2) is None

        # No row was lost or duplicated across the two pages.
        page1_ids = {m.id for m in page1.messages}
        page2_ids = {m.id for m in page2.messages}
        assert not (page1_ids & page2_ids), "pages must not overlap"
        assert len(page1_ids | page2_ids) == 250

    async def test_get_messages_since_respects_caller_limit(self) -> None:
        """Caller-supplied limit (e.g. 10) is honored, not silently widened."""
        session = _make_session()
        service = ConversationService(session)

        base = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
        # Over-fetch by 1: feed 11 to test limit=10.
        rows = [
            _make_message_row(
                content=f"m{i}",
                created_at=base + timedelta(seconds=i),
            )
            for i in range(11)
        ]
        _wire_execute_returning(session, rows)

        resp = await service.get_messages_since(
            since="2026-05-01T11:59:00+00:00",
            limit=10,
        )

        assert len(resp.messages) == 10
        assert resp.has_more is True


# ---------------------------------------------------------------------------
# Schema-shape helper
# ---------------------------------------------------------------------------


def _read_next_cursor(resp: Any) -> str | None:
    """Read the 'next page' cursor regardless of which field name ships.

    The spec calls for ``next_since`` on the response schema, while the
    existing schema uses ``next_cursor``. The developer may add ``next_since``
    as a new field or rename — accept whichever is present so the test only
    asserts on the *contract*, not the field name.
    """
    next_since = getattr(resp, "next_since", None)
    if next_since is not None:
        return str(next_since)
    next_cursor = getattr(resp, "next_cursor", None)
    return str(next_cursor) if next_cursor is not None else None


# ---------------------------------------------------------------------------
# export_conversation — V1.x Item 10 truncation contract
# ---------------------------------------------------------------------------


class TestExportConversationTruncation:
    """``export_conversation`` must surface truncation when row count > cap.

    Pre-V1.x behaviour: silent ``LIMIT 500`` — long conversations exported
    only the most recent 500 messages with NO indicator. V1.x Item 10 bumps
    the cap to ``EXPORT_MESSAGE_LIMIT`` (5000), appends a markdown footer
    when the cap is hit, and emits a ``conversation_export_truncated``
    structlog warning so operators can spot real-world hits.
    """

    async def test_export_under_limit_no_truncation_footer(self) -> None:
        """100 messages → no footer, no truncation warning."""
        import structlog.testing

        session = _make_session()
        service = ConversationService(session)

        base = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
        rows = [
            _make_message_row(content=f"m{i}", created_at=base + timedelta(seconds=i))
            for i in range(100)
        ]
        _wire_execute_returning(session, rows)

        with structlog.testing.capture_logs() as captured:
            output = await service.export_conversation(
                project_id=None,
                session_id="sess-1",
            )

        # No truncation footer — the marker phrase MUST NOT appear.
        assert "export contains the first" not in output.lower()
        # And no structlog warning.
        truncation_logs = [e for e in captured if e.get("event") == "conversation_export_truncated"]
        assert truncation_logs == []
        # Sanity: header is present.
        assert "Konusma Gecmisi" in output

    async def test_export_at_limit_no_truncation_footer(self) -> None:
        """Exactly EXPORT_MESSAGE_LIMIT rows → no footer (boundary case).

        The service over-fetches by one (limit+1) so it can detect "more
        rows exist". When the DB returns exactly ``EXPORT_MESSAGE_LIMIT``
        rows, the ``> EXPORT_MESSAGE_LIMIT`` check is false and we MUST
        NOT emit the footer.
        """
        import structlog.testing

        session = _make_session()
        service = ConversationService(session)

        base = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
        rows = [
            _make_message_row(content=f"m{i}", created_at=base + timedelta(seconds=i))
            for i in range(EXPORT_MESSAGE_LIMIT)
        ]
        _wire_execute_returning(session, rows)

        with structlog.testing.capture_logs() as captured:
            output = await service.export_conversation(
                project_id=None,
                session_id="sess-1",
            )

        assert "export contains the first" not in output.lower()
        truncation_logs = [e for e in captured if e.get("event") == "conversation_export_truncated"]
        assert truncation_logs == []

    async def test_export_over_limit_appends_truncation_footer(self) -> None:
        """LIMIT+1 rows → footer present, only LIMIT messages rendered."""
        import structlog.testing

        session = _make_session()
        service = ConversationService(session)

        base = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
        # Service over-fetches by one (limit+1) — feed exactly that many
        # rows to simulate "5001 messages exist".
        rows = [
            _make_message_row(content=f"m{i}", created_at=base + timedelta(seconds=i))
            for i in range(EXPORT_MESSAGE_LIMIT + 1)
        ]
        _wire_execute_returning(session, rows)

        with structlog.testing.capture_logs() as captured:
            output = await service.export_conversation(
                project_id=None,
                session_id="sess-1",
            )

        # Footer present.
        assert "export contains the first" in output.lower()
        # The cap should be mentioned in the footer for user clarity.
        assert str(EXPORT_MESSAGE_LIMIT) in output

        # Header reports the trimmed count, NOT the over-fetched total.
        assert f"Mesaj Sayisi: {EXPORT_MESSAGE_LIMIT}" in output

        # Only EXPORT_MESSAGE_LIMIT messages were rendered (the over-fetched
        # row is trimmed). Easy proxy: the LAST rendered message in the body
        # is m{LIMIT-1}, NOT m{LIMIT}.
        assert f"m{EXPORT_MESSAGE_LIMIT - 1}" in output
        assert f"m{EXPORT_MESSAGE_LIMIT}\n" not in output

        # structlog warning emitted exactly once with the right shape.
        truncation_logs = [e for e in captured if e.get("event") == "conversation_export_truncated"]
        assert len(truncation_logs) == 1
        evt = truncation_logs[0]
        assert evt["log_level"] == "warning"
        assert evt["delivered"] == EXPORT_MESSAGE_LIMIT
        assert evt["cap"] == EXPORT_MESSAGE_LIMIT
        assert evt["session_id"] == "sess-1"
        assert evt.get("more_than_cap") is True

    async def test_export_over_limit_logs_warning(self) -> None:
        """Truncation MUST emit a structlog warning event for observability.

        Independent of footer rendering — operators rely on the
        ``conversation_export_truncated`` event to alert when real users
        hit the cap. Pinning the event name + level here keeps drive-by
        edits from accidentally lowering it to ``info``.
        """
        import structlog.testing

        session = _make_session()
        service = ConversationService(session)

        # Use project_id (uuid) path to confirm the warning carries it.
        project_id = uuid.uuid4()
        base = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
        rows = [
            _make_message_row(content=f"m{i}", created_at=base + timedelta(seconds=i))
            for i in range(EXPORT_MESSAGE_LIMIT + 1)
        ]
        _wire_execute_returning(session, rows)

        with structlog.testing.capture_logs() as captured:
            await service.export_conversation(
                project_id=project_id,
                session_id=None,
            )

        truncation_logs = [e for e in captured if e.get("event") == "conversation_export_truncated"]
        assert len(truncation_logs) == 1
        evt = truncation_logs[0]
        assert evt["log_level"] == "warning"
        # project_id was supplied — must be reported (as a string).
        assert evt["project_id"] == str(project_id)
        # session_id was None — must serialise as None.
        assert evt["session_id"] is None
