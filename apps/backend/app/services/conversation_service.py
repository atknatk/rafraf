"""Konusma gecmisi kayit ve sorgulama servisi."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import asc, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import MessageTooLargeError
from app.models.message import Message
from app.schemas.conversation import (
    ConversationHistoryResponse,
    MessageRatingRequest,
    MessageResponse,
)

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

_DEFAULT_LIMIT = 50
_MAX_LIMIT = 200

# Hard cap (bytes, UTF-8) on a single Message.content row.
#
# Why this exists:
# - Postgres TEXT has no length cap, so without a service-side guard a single
#   huge assistant response (or a malicious crafted payload) would persist and
#   later be downloaded by every client that fetches history.
# - iOS uses JSONDecoder which loads the entire string in memory; on older
#   devices a 10MB+ message can OOM the chat view.
# - User input is already capped on iOS (SendMessageUseCase 4096 chars), but
#   assistant output is NOT capped anywhere on the iOS side, so it MUST be
#   capped here.
#
# Two enforcement modes (decided at the call site by `role`):
# - "user"      -> raise MessageTooLargeError (HTTP 413)
# - "assistant" -> truncate to (cap - 200 byte sentinel margin) and append a
#                  human-readable sentinel; emit a structlog warning event
#                  `assistant_message_truncated` with original byte size.
MAX_MESSAGE_CONTENT_BYTES = 1_000_000  # 1 MB


class ConversationService:
    """Chat mesajlarini PostgreSQL'e kaydeder ve sayfalayarak getirir."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save_message(
        self,
        *,
        session_id: str,
        user_id: str,
        role: str,
        content: str,
        project_id: uuid.UUID | None = None,
        agent_id: str | None = None,
        model_used: str | None = None,
        tokens_used: int | None = None,
    ) -> Message:
        """Mesaji veritabanina kaydeder.

        Enforces ``MAX_MESSAGE_CONTENT_BYTES`` per role:
        - ``role == "user"``: oversize payloads raise ``MessageTooLargeError``
          (HTTP 413). The DB layer is never touched on the rejection path.
        - any other role (assistant, system, tool, ...): oversize payloads
          are truncated UTF-8-safely to ``MAX_MESSAGE_CONTENT_BYTES - 200``
          bytes and a human-readable sentinel is appended so the client
          can render a "truncated" indicator. A ``assistant_message_truncated``
          structlog warning is emitted with original/kept byte counts.
        """
        byte_length = len(content.encode("utf-8"))
        if byte_length > MAX_MESSAGE_CONTENT_BYTES:
            if role == "user":
                # Reject before touching the DB so the rejected payload is
                # never persisted.
                raise MessageTooLargeError(
                    message=(
                        f"User message content is {byte_length} bytes, "
                        f"which exceeds the maximum allowed "
                        f"{MAX_MESSAGE_CONTENT_BYTES} bytes."
                    ),
                )

            # Non-user (assistant/tool/system): truncate with a sentinel so the
            # conversation remains usable. UTF-8 safe: slice bytes then decode
            # with errors="ignore" to drop any partial trailing code unit.
            keep_bytes = MAX_MESSAGE_CONTENT_BYTES - 200
            kept = content.encode("utf-8")[:keep_bytes].decode("utf-8", errors="ignore")
            kept_bytes = len(kept.encode("utf-8"))
            sentinel = (
                f"\n\n[…truncated by server: original was {byte_length} "
                f"bytes, kept first {kept_bytes} bytes…]"
            )
            content = kept + sentinel
            logger.warning(
                "assistant_message_truncated",
                session_id=session_id,
                role=role,
                original_bytes=byte_length,
                kept_bytes=kept_bytes,
                project_id=str(project_id) if project_id else None,
            )

        msg = Message(
            session_id=session_id,
            user_id=user_id,
            project_id=project_id,
            agent_id=agent_id,
            role=role,
            content=content,
            model_used=model_used,
            tokens_used=tokens_used,
        )
        self._session.add(msg)
        await self._session.flush()
        logger.debug(
            "message_saved",
            session_id=session_id,
            role=role,
            project_id=str(project_id) if project_id else None,
        )
        return msg

    async def get_history(
        self,
        *,
        project_id: uuid.UUID | None = None,
        session_id: str | None = None,
        limit: int = _DEFAULT_LIMIT,
        cursor: str | None = None,
    ) -> ConversationHistoryResponse:
        """Proje veya session bazinda mesaj gecmisini dondurur.

        cursor: onceki sayfanin en eski mesajinin created_at ISO stringi.
        """
        limit = min(max(1, limit), _MAX_LIMIT)

        stmt = select(Message)

        if project_id is not None:
            stmt = stmt.where(Message.project_id == project_id)
        elif session_id is not None:
            stmt = stmt.where(Message.session_id == session_id)
        else:
            return ConversationHistoryResponse(
                messages=[], total=0, has_more=False, next_cursor=None
            )

        if cursor is not None:
            # cursor = created_at ISO string; onceki sayfadan daha eski mesajlari al
            stmt = stmt.where(Message.created_at < cursor)

        stmt = stmt.order_by(desc(Message.created_at)).limit(limit + 1)
        result = await self._session.execute(stmt)
        rows = list(result.scalars())

        has_more = len(rows) > limit
        if has_more:
            rows = rows[:limit]

        # Kronolojik siraya cevir (eski -> yeni)
        rows.reverse()

        next_cursor: str | None = None
        if has_more and rows:
            next_cursor = rows[0].created_at.isoformat()

        responses = [
            MessageResponse(
                id=m.id,
                session_id=m.session_id,
                user_id=m.user_id,
                project_id=m.project_id,
                agent_id=m.agent_id,
                role=m.role,
                content=m.content,
                model_used=m.model_used,
                tokens_used=m.tokens_used,
                created_at=m.created_at.isoformat(),
                rating=m.rating,
                rating_note=m.rating_note,
                rated_at=m.rated_at.isoformat() if m.rated_at else None,
            )
            for m in rows
        ]

        return ConversationHistoryResponse(
            messages=responses,
            total=len(responses),
            has_more=has_more,
            next_cursor=next_cursor,
        )

    async def export_conversation(
        self,
        project_id: uuid.UUID | None,
        session_id: str | None,
    ) -> str:
        """Konusmayi markdown formatinda disa aktar.

        Returns the conversation as a formatted string.
        """
        stmt = select(Message).order_by(Message.created_at.asc()).limit(500)
        if project_id:
            stmt = stmt.where(Message.project_id == project_id)
        elif session_id:
            stmt = stmt.where(Message.session_id == session_id)

        result = await self._session.execute(stmt)
        messages = list(result.scalars().all())

        if not messages:
            return "# Konusma Gecmisi\n\nMesaj bulunamadi.\n"

        lines: list[str] = [
            "# Konusma Gecmisi",
            f"Tarih: {datetime.now(tz=UTC).strftime('%Y-%m-%d %H:%M UTC')}",
            f"Mesaj Sayisi: {len(messages)}",
            "",
            "---",
            "",
        ]

        for msg in messages:
            role_label = "**Kullanici**" if msg.role == "user" else "**Claude**"
            created = msg.created_at.strftime("%H:%M") if msg.created_at else ""
            lines.append(f"### {role_label} _{created}_")
            lines.append("")
            lines.append(msg.content)
            if msg.model_used:
                lines.append("")
                lines.append(f"*Model: {msg.model_used}*")
            if msg.tokens_used:
                lines.append(f"*Tokenlar: {msg.tokens_used}*")
            lines.append("")
            lines.append("---")
            lines.append("")

        return "\n".join(lines)

    async def rate_message(
        self,
        *,
        message_id: str,
        user_id: str,
        body: MessageRatingRequest,
    ) -> Message | None:
        """Mesaj degerlendirmesini kaydeder (thumbs up/down).

        Sadece kendi mesajlarini degerlendirmeye izin verilir.
        Mesaj bulunamazsa None dondurur.
        """
        stmt = select(Message).where(
            Message.id == message_id,
            Message.user_id == user_id,
        )
        result = await self._session.execute(stmt)
        msg = result.scalar_one_or_none()

        if msg is None:
            return None

        msg.rating = body.rating
        msg.rating_note = body.note
        msg.rated_at = datetime.now(tz=UTC)
        await self._session.flush()
        logger.info(
            "message_rated",
            message_id=message_id,
            rating=body.rating,
        )
        return msg

    async def search_messages(
        self,
        user_id: str,
        query: str,
        project_id: str | None = None,
        limit: int = 20,
    ) -> list[Message]:
        """Full-text mesaj arama."""
        stmt = (
            select(Message)
            .where(Message.user_id == user_id)
            .where(Message.content.ilike(f"%{query}%"))
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        if project_id:
            stmt = stmt.where(Message.project_id == uuid.UUID(project_id))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_recent_messages(
        self,
        *,
        limit: int = 1,
    ) -> ConversationHistoryResponse:
        """Tum sessionlardan en son N mesaji dondurur (created_at desc).

        Home ekraninda "son sohbet" preview kartini beslemek icin kullanilir.
        """
        clamped = min(max(1, limit), 20)
        stmt = select(Message).order_by(desc(Message.created_at)).limit(clamped)
        result = await self._session.execute(stmt)
        rows = list(result.scalars())

        # Kronolojik siraya cevir (eski -> yeni) — UI tipik tuketim sirasi.
        rows.reverse()

        responses = [
            MessageResponse(
                id=m.id,
                session_id=m.session_id,
                user_id=m.user_id,
                project_id=m.project_id,
                agent_id=m.agent_id,
                role=m.role,
                content=m.content,
                model_used=m.model_used,
                tokens_used=m.tokens_used,
                created_at=m.created_at.isoformat(),
                rating=m.rating,
                rating_note=m.rating_note,
                rated_at=m.rated_at.isoformat() if m.rated_at else None,
            )
            for m in rows
        ]

        return ConversationHistoryResponse(
            messages=responses,
            total=len(responses),
            has_more=False,
            next_cursor=None,
        )

    async def get_messages_since(
        self,
        *,
        since: str,
        project_id: uuid.UUID | None = None,
        session_id: str | None = None,
        limit: int = _MAX_LIMIT,
    ) -> ConversationHistoryResponse:
        """Return messages created after the given ISO timestamp.

        Used for offline sync: iOS fetches missed messages on reconnect.

        Pagination contract (so iOS can keep paging without silent loss):
        - The query over-fetches by one row (``LIMIT limit + 1``) to detect
          whether more rows exist beyond the caller's window.
        - If ``len(rows) > limit`` the extra row is trimmed and
          ``has_more=True``.
        - ``next_cursor`` is the ISO 8601 ``created_at`` of the LAST DELIVERED
          row when (and only when) ``has_more=True``. The next call should
          pass ``since=next_cursor`` to receive the subsequent page.
        - When ``has_more=False`` the response carries ``next_cursor=None``.

        The schema field name is ``next_cursor`` (kept for backwards-compat
        with existing iOS history-fetch code that already reads this field
        on ``ConversationHistoryResponse``).
        """
        since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
        # Clamp caller's limit defensively (mirrors get_history at line 141).
        # Today the missed-messages route does not expose `limit`, but a future
        # caller passing 10_000_000 would otherwise OOM both DB and serializer.
        limit = min(max(1, limit), _MAX_LIMIT)
        stmt = select(Message).where(Message.created_at > since_dt)

        if project_id is not None:
            stmt = stmt.where(Message.project_id == project_id)
        elif session_id is not None:
            stmt = stmt.where(Message.session_id == session_id)

        # Honor the caller's limit; over-fetch by one to detect more pages.
        # TODO: tie-breaker on created_at — under burst load multiple rows can
        # share the same microsecond and the cursor (created_at only, no `id`
        # secondary key) would skip ties. Add ORDER BY created_at, id ASC and
        # a composite cursor when burst-load tests show the regression.
        stmt = stmt.order_by(asc(Message.created_at)).limit(limit + 1)
        result = await self._session.execute(stmt)
        rows = list(result.scalars())

        has_more = len(rows) > limit
        if has_more:
            rows = rows[:limit]

        next_cursor: str | None = None
        if has_more and rows:
            next_cursor = rows[-1].created_at.isoformat()

        responses = [
            MessageResponse(
                id=m.id,
                session_id=m.session_id,
                user_id=m.user_id,
                project_id=m.project_id,
                agent_id=m.agent_id,
                role=m.role,
                content=m.content,
                model_used=m.model_used,
                tokens_used=m.tokens_used,
                created_at=m.created_at.isoformat(),
                rating=m.rating,
                rating_note=m.rating_note,
                rated_at=m.rated_at.isoformat() if m.rated_at else None,
            )
            for m in rows
        ]

        return ConversationHistoryResponse(
            messages=responses,
            total=len(responses),
            has_more=has_more,
            next_cursor=next_cursor,
        )
