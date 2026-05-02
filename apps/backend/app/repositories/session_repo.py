"""Session repository — async database access layer."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import Session

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


CostPeriod = Literal["current_month", "last_month", "current_week", "last_7_days"]


class SessionRepository:
    """DB access layer for sessions table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, user_id: uuid.UUID) -> Session:
        """Create a new session record."""
        record = Session(user_id=user_id)
        self._session.add(record)
        await self._session.flush()
        await self._session.refresh(record)
        await logger.ainfo("session_created", session_id=str(record.id))
        return record

    async def end_session(self, session_id: uuid.UUID) -> None:
        """Mark a session as ended."""
        now = datetime.now(tz=UTC)
        stmt = update(Session).where(Session.id == session_id).values(ended_at=now, updated_at=now)
        await self._session.execute(stmt)
        await logger.ainfo("session_ended", session_id=str(session_id))

    async def get_by_id(self, session_id: uuid.UUID) -> Session | None:
        """Get a session by ID."""
        query = select(Session).where(Session.id == session_id)
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def get_active_by_user(self, user_id: uuid.UUID) -> list[Session]:
        """Get active (not ended) sessions for a user."""
        query = (
            select(Session)
            .where(Session.user_id == user_id, Session.ended_at.is_(None))
            .order_by(Session.started_at.desc())
        )
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def update_stats(
        self,
        session_id: uuid.UUID,
        *,
        message_count_increment: int = 0,
        tokens_input: int = 0,
        tokens_output: int = 0,
    ) -> None:
        """Increment session statistics (message count + token totals).

        Cost tracking removed alongside cost service deletion (T0.7+T0.8);
        the ``sessions.total_cost_usd`` column is left in the schema for
        backwards compatibility but is no longer written by the application.
        """
        record = await self.get_by_id(session_id)
        if record is None:
            return
        record.message_count += message_count_increment
        current_tokens = record.total_tokens_used or {"input": 0, "output": 0}
        input_val = current_tokens.get("input", 0)
        output_val = current_tokens.get("output", 0)
        current_tokens["input"] = (
            int(input_val) if isinstance(input_val, (int, float)) else 0
        ) + tokens_input
        current_tokens["output"] = (
            int(output_val) if isinstance(output_val, (int, float)) else 0
        ) + tokens_output
        record.total_tokens_used = current_tokens
        await self._session.flush()

    async def update_session_cost(
        self,
        session_id: uuid.UUID,
        *,
        user_id: uuid.UUID,
        total_cost_usd: Decimal | float,
        total_input_tokens: int = 0,
        total_output_tokens: int = 0,
        total_cache_creation_tokens: int = 0,
        total_cache_read_tokens: int = 0,
    ) -> bool:
        """Cumulative ADD of per-message cost + tokens onto a session row.

        Wired by ``ClaudeCodeRunner`` when an ``event.session.result``
        envelope arrives (T1.1 surface; T2.5 persistence). Each invocation
        ADDs to the existing column values via ``COALESCE`` — never
        replaces — so a multi-turn session correctly aggregates across
        many ``claude -p`` invocations.

        T2.5-fix (UPSERT): No prior row is created at WS-connect for the
        runtime ``session_id`` (the WS session UUID4 is generated in
        ``websocket.py`` without an INSERT to ``sessions``), so the
        legacy plain-UPDATE matched zero rows in production and cost data
        was silently dropped. We now use PostgreSQL
        ``INSERT ... ON CONFLICT DO UPDATE`` so the first call seeds the
        row (with a valid ``user_id`` FK) and subsequent calls accumulate
        cumulatively. ``user_id`` is therefore mandatory — without it a
        fresh INSERT would violate the NOT NULL FK on ``sessions.user_id``.

        Args:
            session_id: WebSocket session UUID (``sessions.id``).
            user_id: Owner of the WS session — required because the row
                may not exist yet and ``user_id`` is NOT NULL with FK
                ``sessions.user_id -> users.id``.
            total_cost_usd: ``result.total_cost_usd`` from the envelope.
                Negative values are rejected (no refund semantics).
            total_input_tokens: Sum of per-model ``input_tokens``.
            total_output_tokens: Sum of per-model ``output_tokens``.
            total_cache_creation_tokens: Anthropic prompt-cache WRITE.
            total_cache_read_tokens: Anthropic prompt-cache READ.

        Returns:
            Always ``True`` — UPSERT either inserts a fresh row or
            updates the existing one. Kept as ``bool`` for API parity
            with the legacy signature (callers may discard the value).
        """
        cost = Decimal(str(total_cost_usd))
        if cost < 0:
            cost = Decimal("0")

        # PostgreSQL UPSERT — first call seeds the row, subsequent calls
        # accumulate via ON CONFLICT DO UPDATE. The conflict target is the
        # primary key (``id``); the SET clause uses qualified column refs
        # against the live row (``Session.<col>``) so the addition reads
        # the existing value, not the INSERT-time value.
        insert_stmt = pg_insert(Session).values(
            id=session_id,
            user_id=user_id,
            total_cost_usd=cost,
            total_input_tokens=total_input_tokens,
            total_output_tokens=total_output_tokens,
            total_cache_creation_tokens=total_cache_creation_tokens,
            total_cache_read_tokens=total_cache_read_tokens,
            cost_updated_at=func.now(),
        )
        upsert_stmt = insert_stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "total_cost_usd": (func.coalesce(Session.total_cost_usd, Decimal("0")) + cost),
                "total_input_tokens": (
                    func.coalesce(Session.total_input_tokens, 0) + total_input_tokens
                ),
                "total_output_tokens": (
                    func.coalesce(Session.total_output_tokens, 0) + total_output_tokens
                ),
                "total_cache_creation_tokens": (
                    func.coalesce(Session.total_cache_creation_tokens, 0)
                    + total_cache_creation_tokens
                ),
                "total_cache_read_tokens": (
                    func.coalesce(Session.total_cache_read_tokens, 0) + total_cache_read_tokens
                ),
                "cost_updated_at": func.now(),
                "updated_at": func.now(),
            },
        )
        await self._session.execute(upsert_stmt)
        await logger.adebug(
            "session_cost_upserted",
            session_id=str(session_id),
            user_id=str(user_id),
            cost_increment=str(cost),
        )
        return True

    async def list_costs_for_user_in_period(
        self,
        *,
        user_id: uuid.UUID,
        period_start: datetime,
        period_end: datetime | None = None,
    ) -> list[Session]:
        """Return all sessions for a user with cost recorded inside the window.

        Filter is on ``cost_updated_at`` (not ``started_at``) so a long-lived
        session whose cost was last touched inside the window is still
        attributed to that period — matches the intuition "show me what I
        spent in May" rather than "show me sessions that started in May".
        """
        stmt = (
            select(Session)
            .where(
                Session.user_id == user_id,
                Session.cost_updated_at.is_not(None),
                Session.cost_updated_at >= period_start,
            )
            .order_by(Session.cost_updated_at.desc())
        )
        if period_end is not None:
            stmt = stmt.where(Session.cost_updated_at < period_end)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Period helpers — pure functions so unit tests can verify boundaries without
# spinning up a DB session.
# ---------------------------------------------------------------------------


def resolve_period_window(
    period: CostPeriod,
    *,
    now: datetime | None = None,
) -> tuple[datetime, datetime | None, str]:
    """Translate a period label to ``(start, end, label)``.

    ``end`` is ``None`` for periods that flow up to "right now" (i.e. the
    SQL filter is ``>= start`` only). The ``label`` is the canonical string
    surfaced in the API response (e.g. ``"2026-05"`` for current month).
    """
    current = now or datetime.now(tz=UTC)
    if period == "current_month":
        start = current.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return start, None, f"{start.year:04d}-{start.month:02d}"
    if period == "last_month":
        first_of_current = current.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        # Step back one second into the previous month, then snap to its 1st.
        last_month_anchor = first_of_current - timedelta(seconds=1)
        start = last_month_anchor.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return start, first_of_current, f"{start.year:04d}-{start.month:02d}"
    if period == "current_week":
        # ISO week — Monday as start of week.
        midnight = current.replace(hour=0, minute=0, second=0, microsecond=0)
        start = midnight - timedelta(days=midnight.weekday())
        iso_year, iso_week, _ = start.isocalendar()
        return start, None, f"{iso_year:04d}-W{iso_week:02d}"
    if period == "last_7_days":
        start = current - timedelta(days=7)
        return start, None, "last_7_days"
    # Defensive — Literal[...] guarantees we never hit this branch, but
    # mypy strict requires the explicit raise.
    raise ValueError(f"Unsupported period: {period!r}")
