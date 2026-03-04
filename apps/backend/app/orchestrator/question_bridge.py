"""Question bridge - forwards Claude Code questions to iOS and waits for answers."""

import asyncio
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from uuid import uuid4

import structlog

from app.schemas.messages import (
    MessageType,
    QuestionOptionPayload,
    QuestionPayload,
)

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

# Default timeout for waiting for user answer (seconds)
_QUESTION_TIMEOUT_SECONDS: int = 300

# Type alias for the WebSocket send callback
SendToIosCallback = Callable[[dict[str, object]], Coroutine[object, object, None]]


class QuestionBridge:
    """Bridges questions between claude -p subprocess and iOS client.

    When claude -p calls AskUserQuestion, this bridge:
    1. Formats the question as a QUESTION WebSocket message
    2. Sends it to the iOS client
    3. Waits for the user's answer via an asyncio.Future
    4. Returns the answer to be fed back into claude -p --resume
    """

    def __init__(self) -> None:
        self._pending: dict[str, asyncio.Future[str]] = {}

    async def ask_user(
        self,
        *,
        question_payload: dict[str, object],
        send_to_ios: SendToIosCallback,
        session_id: str,
    ) -> str | None:
        """Send a question to iOS and wait for the answer.

        Args:
            question_payload: AskUserQuestion input from Claude Code.
                Expected keys: "question" (str), "options" (list of dicts).
            send_to_ios: Async callback that sends a JSON dict to iOS via WebSocket.
            session_id: Current WebSocket session ID.

        Returns:
            User's answer text, or None if timed out.
        """
        approval_id = str(uuid4())

        # Parse question from Claude Code format
        question_text = str(question_payload.get("question", ""))
        raw_options = question_payload.get("options", [])

        # Build QuestionPayload for iOS
        options: list[QuestionOptionPayload] = []
        if isinstance(raw_options, list):
            for i, opt in enumerate(raw_options):
                if isinstance(opt, dict):
                    options.append(
                        QuestionOptionPayload(
                            id=str(i),
                            label=str(opt.get("label", f"Option {i + 1}")),
                            style="default",
                        )
                    )

        question_msg = QuestionPayload(
            approval_id=approval_id,
            question=question_text,
            context=str(question_payload.get("context", "")) or None,
            options=options if options else [],
            timeout_seconds=_QUESTION_TIMEOUT_SECONDS,
            category="claude_code_question",
        )

        # Create future for answer
        loop = asyncio.get_running_loop()
        future: asyncio.Future[str] = loop.create_future()
        self._pending[approval_id] = future

        # Send question to iOS
        ws_message: dict[str, object] = {
            "id": str(uuid4()),
            "type": MessageType.QUESTION.value,
            "content": question_msg.model_dump(exclude_none=True),
            "metadata": {
                "timestamp": datetime.now(tz=UTC).isoformat(),
                "session_id": session_id,
                "direction": "server_to_client",
            },
        }

        await send_to_ios(ws_message)

        await logger.ainfo(
            "question_sent_to_ios",
            approval_id=approval_id,
            question=question_text[:100],
        )

        # Wait for answer with timeout
        try:
            answer = await asyncio.wait_for(future, timeout=_QUESTION_TIMEOUT_SECONDS)
            await logger.ainfo(
                "question_answered",
                approval_id=approval_id,
                answer=answer[:100],
            )
            return answer
        except TimeoutError:
            await logger.awarning(
                "question_timeout",
                approval_id=approval_id,
            )
            return None
        finally:
            self._pending.pop(approval_id, None)

    def submit_answer(self, approval_id: str, answer: str) -> bool:
        """Submit a user's answer for a pending question.

        Called when iOS sends APPROVAL_RESPONSE or QUESTION_RESPONSE.

        Args:
            approval_id: The approval ID from the QUESTION message.
            answer: The user's answer text.

        Returns:
            True if a pending question was found and answered.
        """
        future = self._pending.get(approval_id)
        if future is None or future.done():
            return False
        future.set_result(answer)
        return True

    @property
    def pending_count(self) -> int:
        """Number of pending unanswered questions."""
        return len(self._pending)


# Module-level singleton
_bridge: QuestionBridge | None = None


def get_question_bridge() -> QuestionBridge:
    """Get or create the global QuestionBridge singleton.

    Returns:
        Global QuestionBridge instance.
    """
    global _bridge  # noqa: PLW0603
    if _bridge is None:
        _bridge = QuestionBridge()
    return _bridge
