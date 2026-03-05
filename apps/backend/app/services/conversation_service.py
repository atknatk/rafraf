"""Konusma gecmisi kayit ve sorgulama servisi."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import asc, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message
from app.schemas.conversation import ConversationHistoryResponse, MessageResponse

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

_DEFAULT_LIMIT = 50
_MAX_LIMIT = 200


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
        """Mesaji veritabanina kaydeder."""
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
        """
        since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
        stmt = select(Message).where(Message.created_at > since_dt)

        if project_id is not None:
            stmt = stmt.where(Message.project_id == project_id)
        elif session_id is not None:
            stmt = stmt.where(Message.session_id == session_id)

        stmt = stmt.order_by(asc(Message.created_at)).limit(limit)
        result = await self._session.execute(stmt)
        rows = list(result.scalars())

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
            )
            for m in rows
        ]

        return ConversationHistoryResponse(
            messages=responses,
            total=len(responses),
            has_more=False,
            next_cursor=None,
        )
