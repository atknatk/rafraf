"""Subagent read service — REST hydration of persisted subagent state.

Owned by V1.x Item 9. Wraps ``SubagentRepository.list_subagents_for_session``
so the REST route stays a thin transport layer and the mapping from the
ORM ``Subagent`` model to the public ``SubagentResponse`` DTO has one
canonical implementation.

Persistence is "best effort" (see ``app.models.subagent`` docstring); a
crashed bridge mid-stream may leave a row stuck in ``status='spawned'``.
This service does not attempt reconciliation — that's a future-V2 concern.

Auth posture (V1.x) — see route docstring + reviewer feedback Important #3.
The ``bridges`` table has NO ``user_id`` column today (see
``app/models/bridge.py``), so a bridges→user JOIN cannot be added without
a schema migration that's out of V1.x scope. The route is JWT-gated
(authenticated only) and the deployment is single-tenant TestFlight, so
the IDOR risk is effectively zero in the V1.x window. T1.x will land a
``bridges.user_id`` FK and tighten the filter here.
"""

from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.subagent import Subagent
from app.repositories.subagent_repo import SubagentRepository
from app.schemas.subagents import SubagentResponse, SubagentStatusLiteral

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

# Defensive cap on the number of rows returned per request. Typical session
# has < 50 subagents (V1.x design assumption per docs/10 §6.1.1); bumping
# 10x to 500 keeps the worst-case payload small (~150KB) while shielding
# the route from a runaway producer that might spawn thousands. V2 will
# add cursor-based pagination if real-world sessions exceed this.
_DEFAULT_LIMIT = 500

# Whitelist of allowed status values as they appear on the ORM row. Anything
# outside this set is logged as ``subagent_status_coerced`` and mapped to
# ``"failed"`` (NOT ``"spawned"``) — the conservative choice. Mapping an
# unknown value to ``spawned`` would silently re-render a long-finished
# in-flight task as fresh work; ``failed`` instead surfaces the anomaly so
# operators investigate. The frozen Pydantic response cannot accept the
# raw value because ``SubagentStatusLiteral`` is a closed set.
_VALID_STATUSES: frozenset[str] = frozenset({"spawned", "in_progress", "completed", "failed"})


def _coerce_status(raw: str | None, *, session_id: str, task_id: str) -> SubagentStatusLiteral:
    """Map a raw ``Subagent.status`` value to the public Literal vocabulary.

    Unknown / future status values are logged once per row and surfaced
    to iOS as ``"failed"``. Reviewer feedback (Important #4): the prior
    silent fallback to ``"spawned"`` masked real corruption — operators
    only saw "fresh spawn" indicators while a runaway bridge schema was
    actually emitting unmappable enum values.
    """
    if raw in _VALID_STATUSES:
        # Narrow ``str`` to the Literal — mypy can't infer this from the
        # frozenset membership, so cast at the boundary.
        return raw  # type: ignore[return-value]

    logger.warning(
        "subagent_status_coerced",
        raw_status=raw,
        coerced_to="failed",
        session_id=session_id,
        task_id=task_id,
    )
    return "failed"


def _to_response(row: Subagent) -> SubagentResponse:
    """Project a ``Subagent`` ORM row to its public REST DTO.

    The mapping is field-for-field with the iOS ``SubagentRestDTO`` so the
    mobile cache key (``Subagent.id`` = bridge ``task_id``) matches between
    REST hydration and WS push paths. See ``SubagentResponse`` docstring
    for the contract rationale.
    """
    return SubagentResponse(
        # IMPORTANT: ``id`` is the bridge ``task_id`` (string), NOT the
        # SQL UUID — iOS keys its in-memory cache by ``Subagent.id`` which
        # the WS push mapper feeds from ``content.task_id``. Sending the
        # SQL UUID here would cause REST-hydrated rows to be cached under
        # a different key than the next WS update, producing duplicates.
        id=row.task_id,
        db_id=row.id,
        parent_id=row.parent_session_id,
        session_id=row.session_id,
        status=_coerce_status(
            row.status,
            session_id=row.session_id,
            task_id=row.task_id,
        ),
        # Descriptive metadata — pass through verbatim. iOS handles the
        # name-vs-description fallback in its mapper (``dto.name ??
        # dto.subagentType ?? "subagent"``); the backend should NOT
        # collapse these fields here or iOS loses the ability to
        # distinguish "spawn-time label" from "long description".
        name=row.name,
        description=row.description,
        prompt_preview=row.prompt_preview,
        subagent_type=row.subagent_type,
        isolation=row.isolation,
        # Live-only fields not persisted today — always null on REST.
        # iOS treats null as "no in-flight progress information" and
        # falls back to the live WS ``subagent.progress`` stream.
        activity=None,
        progress_percent=None,
        # Terminal payload (from ``system/task_notification``). JSON key
        # is ``summary`` (NOT ``output_summary``) so iOS decodes it via
        # the obvious ``dto.summary`` field — see reviewer feedback
        # Important #1.
        summary=row.summary,
        total_tokens=row.total_tokens,
        tool_uses=row.tool_uses,
        duration_ms=row.duration_ms,
        # Timestamps — UTC; Pydantic serialises as ISO 8601.
        started_at=row.spawned_at,
        updated_at=row.updated_at,
        completed_at=row.completed_at,
    )


class SubagentService:
    """Read-only service for the ``subagents`` table.

    Mirrors the ``ConversationService`` style: thin wrapper around the
    repository, no transactional boundaries (the route owns commits).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = SubagentRepository(session)

    async def list_for_session(
        self,
        session_id: str,
        *,
        limit: int = _DEFAULT_LIMIT,
    ) -> list[SubagentResponse]:
        """Return every persisted subagent for a claude session.

        Ordered by ``spawned_at ASC`` (chronological — matches the order
        iOS renders the subagent timeline). Results are capped at
        ``_DEFAULT_LIMIT`` (500) defensively; pagination is intentionally
        deferred to V2 because real V1.x sessions stay well under the cap
        and a cursor would force an iOS schema change for no near-term
        value.

        Auth posture (V1.x) — see module docstring. No per-user filtering
        because ``bridges`` has no ``user_id`` column yet; the route is
        JWT-gated and the deployment is single-tenant TestFlight, so the
        IDOR risk is effectively zero in the V1.x window. T1.x adds the
        FK and tightens the filter.
        """
        clamped = min(max(1, limit), _DEFAULT_LIMIT)
        rows = await self._repo.list_subagents_for_session(session_id)
        if len(rows) > clamped:
            await logger.awarning(
                "subagent_list_truncated",
                session_id=session_id,
                row_count=len(rows),
                returned=clamped,
            )
            rows = rows[:clamped]
        return [_to_response(row) for row in rows]
