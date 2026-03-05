"""Claude Code runner - subprocess wrapper for claude -p pipe mode."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field

import structlog

from app.core.config import get_settings

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


@dataclass
class _ToolExecution:
    """Tracks a single tool invocation with timing."""

    tool_name: str
    started_at: float  # time.monotonic()
    completed_at: float | None = None
    status: str = "active"  # "active", "completed", "failed"


@dataclass(frozen=True)
class ToolStepInfo:
    """Single step in the execution timeline."""

    id: str
    step_type: str  # "thinking", "tool_calling", "generating"
    label: str
    status: str  # "pending", "active", "completed", "failed"
    tool_name: str | None = None
    duration_seconds: float | None = None
    detail: str | None = None


@dataclass(frozen=True)
class ToolProgressEvent:
    """Rich progress event sent to WebSocket handler."""

    phase: str  # "starting", "thinking", "tool_calling", "generating", "completed"
    phase_label: str
    current_tool: str | None
    percentage: int
    steps: list[ToolStepInfo]


# Type aliases (after ToolProgressEvent so forward ref is resolved)
TextDeltaCallback = Callable[[str, int], Coroutine[object, object, None]]
ToolProgressCallback = Callable[[ToolProgressEvent], Coroutine[object, object, None]]
QuestionCallback = Callable[[dict[str, object]], Coroutine[object, object, str | None]]
StreamEndCallback = Callable[[str], Coroutine[object, object, None]]


@dataclass(frozen=True)
class ClaudeCodeResult:
    """Result from a claude -p execution."""

    session_id: str
    response_text: str
    model_used: str
    duration_ms: int
    is_error: bool


@dataclass
class _StreamState:
    """Mutable state tracked during stream-json parsing."""

    full_text: str = ""
    delta_index: int = 0
    session_id: str = ""
    model: str = ""
    current_tool_name: str = ""
    current_tool_input_json: str = ""
    is_collecting_tool_input: bool = False
    pending_question: dict[str, object] | None = None
    tool_executions: list[_ToolExecution] = field(default_factory=list)
    phase: str = "starting"
    stream_started_at: float = 0.0


class ClaudeCodeError(Exception):
    """Raised when claude -p subprocess fails."""

    def __init__(self, message: str, returncode: int = -1) -> None:
        self.message = message
        self.returncode = returncode
        super().__init__(message)


class ClaudeCodeRunner:
    """Runs claude -p as an async subprocess with stream-json output.

    Parses NDJSON output line-by-line and invokes callbacks for:
    - Text deltas (streamed to iOS via CHAT_STREAM)
    - Tool usage (sent to iOS via PROGRESS)
    - AskUserQuestion (sent to iOS via QUESTION, waits for answer)
    - Stream end (sent to iOS via CHAT_STREAM_END)
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._process: asyncio.subprocess.Process | None = None

    async def run(
        self,
        *,
        prompt: str,
        session_id: str | None = None,
        project_dir: str | None = None,
        on_text_delta: TextDeltaCallback | None = None,
        on_tool_progress: ToolProgressCallback | None = None,
        on_question: QuestionCallback | None = None,
        on_stream_end: StreamEndCallback | None = None,
        append_system_prompt: str | None = None,
    ) -> ClaudeCodeResult:
        """Execute claude -p and stream results via callbacks.

        Args:
            prompt: User message text.
            session_id: Previous session ID to resume (--resume flag).
            on_text_delta: Called for each text token. Args: (delta_text, index).
            on_tool_progress: Called when a tool starts. Args: (tool_name).
            on_question: Called when AskUserQuestion detected. Args: (question_payload).
                          Must return user's answer string, or None to skip.
            on_stream_end: Called when streaming completes. Args: (full_text).
            append_system_prompt: Extra text appended to system prompt.

        Returns:
            ClaudeCodeResult with session_id, response text, model, duration.

        Raises:
            ClaudeCodeError: If subprocess fails or times out.
        """
        cmd = self._build_command(
            prompt=prompt,
            session_id=session_id,
            append_system_prompt=append_system_prompt,
        )

        # CWD öncelik sırası: run()'a geçilen > config default > None (subprocess CWD)
        effective_dir = (
            project_dir
            or self._settings.claude_code_project_dir
            or self._settings.claude_code_default_dir
            or None
        )

        await logger.ainfo(
            "claude_code_starting",
            project_dir=effective_dir,
            model=self._settings.claude_code_model,
            max_turns=self._settings.claude_code_max_turns,
            resume_session=session_id,
        )

        state = _StreamState()

        try:
            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=effective_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            assert self._process.stdout is not None  # noqa: S101
            assert self._process.stderr is not None  # noqa: S101

            # Parse stream-json output line by line
            await self._parse_stream(
                stdout=self._process.stdout,
                state=state,
                on_text_delta=on_text_delta,
                on_tool_progress=on_tool_progress,
                on_question=on_question,
            )

            # Wait for process to finish with timeout
            try:
                _, stderr_bytes = await asyncio.wait_for(
                    self._process.communicate(),
                    timeout=self._settings.claude_code_timeout_seconds,
                )
            except TimeoutError as exc:
                self._process.kill()
                raise ClaudeCodeError(
                    f"claude -p timed out after {self._settings.claude_code_timeout_seconds}s",
                    returncode=-1,
                ) from exc

            returncode = self._process.returncode or 0

            if returncode != 0 and not state.full_text:
                stderr_text = stderr_bytes.decode("utf-8", errors="replace").strip()
                # Detect rate limit errors
                if "rate" in stderr_text.lower() and "limit" in stderr_text.lower():
                    await self._record_rate_limit()
                raise ClaudeCodeError(
                    f"claude -p exited with code {returncode}: {stderr_text}",
                    returncode=returncode,
                )

            # Send completion progress event
            state.phase = "completed"
            if on_tool_progress is not None:
                await on_tool_progress(self._build_progress_event(state))

            # Call stream end callback
            if on_stream_end is not None:
                await on_stream_end(state.full_text)

            await logger.ainfo(
                "claude_code_completed",
                session_id=state.session_id,
                model=state.model or self._settings.claude_code_model,
                text_length=len(state.full_text),
                returncode=returncode,
            )

            return ClaudeCodeResult(
                session_id=state.session_id,
                response_text=state.full_text,
                model_used=state.model or self._settings.claude_code_model,
                duration_ms=0,
                is_error=False,
            )

        except ClaudeCodeError:
            raise
        except Exception as exc:
            await logger.aexception("claude_code_unexpected_error")
            raise ClaudeCodeError(f"Unexpected error: {exc}") from exc
        finally:
            self._process = None

    async def cancel(self) -> None:
        """Cancel a running claude -p process."""
        if self._process is not None and self._process.returncode is None:
            self._process.kill()
            await logger.ainfo("claude_code_cancelled")

    def _build_command(
        self,
        *,
        prompt: str,
        session_id: str | None = None,
        append_system_prompt: str | None = None,
    ) -> list[str]:
        """Build the claude CLI command with all flags.

        Args:
            prompt: User prompt text.
            session_id: Session ID for --resume.
            append_system_prompt: Extra system prompt text.

        Returns:
            Command as list of strings for subprocess.
        """
        cmd: list[str] = [
            self._settings.claude_code_binary,
            "-p",
            prompt,
            "--output-format",
            "stream-json",
            "--model",
            self._settings.claude_code_model,
            "--max-turns",
            str(self._settings.claude_code_max_turns),
            "--verbose",
        ]

        if session_id:
            cmd.extend(["--resume", session_id])

        if append_system_prompt:
            cmd.extend(["--append-system-prompt", append_system_prompt])

        return cmd

    def _build_progress_event(self, state: _StreamState) -> ToolProgressEvent:
        """Build a ToolProgressEvent snapshot from current stream state."""
        steps: list[ToolStepInfo] = []
        now = time.monotonic()

        # Thinking step
        thinking_done = len(state.tool_executions) > 0 or state.phase in (
            "tool_calling",
            "generating",
            "completed",
        )
        steps.append(
            ToolStepInfo(
                id="phase-thinking",
                step_type="thinking",
                label="Dusunuyor...",
                status="completed" if thinking_done else "active",
            )
        )

        # Tool steps
        for i, tex in enumerate(state.tool_executions):
            duration = (tex.completed_at or now) - tex.started_at
            steps.append(
                ToolStepInfo(
                    id=f"tool-{i}",
                    step_type="tool_calling",
                    label=tex.tool_name,
                    status=tex.status,
                    tool_name=tex.tool_name,
                    duration_seconds=round(duration, 1) if tex.completed_at else None,
                )
            )

        # Generating step
        if state.phase in ("generating", "completed"):
            steps.append(
                ToolStepInfo(
                    id="phase-generating",
                    step_type="generating",
                    label="Cevap hazirlaniyor...",
                    status="completed" if state.phase == "completed" else "active",
                )
            )

        # Percentage heuristic
        if state.phase == "starting":
            pct = 5
        elif state.phase == "thinking":
            pct = 10
        elif state.phase == "tool_calling":
            pct = min(20 + len(state.tool_executions) * 10, 80)
        elif state.phase == "generating":
            pct = 85
        else:
            pct = 100

        phase_labels = {
            "starting": "Baslatiliyor...",
            "thinking": "Dusunuyor...",
            "tool_calling": (
                f"Calisiyor: {state.current_tool_name}"
                if state.current_tool_name
                else "Tool calisiyor..."
            ),
            "generating": "Cevap hazirlaniyor...",
            "completed": "Tamamlandi",
        }

        return ToolProgressEvent(
            phase=state.phase,
            phase_label=phase_labels.get(state.phase, state.phase),
            current_tool=state.current_tool_name or None,
            percentage=pct,
            steps=steps,
        )

    async def _parse_stream(
        self,
        *,
        stdout: asyncio.StreamReader,
        state: _StreamState,
        on_text_delta: TextDeltaCallback | None,
        on_tool_progress: ToolProgressCallback | None,
        on_question: QuestionCallback | None,
    ) -> None:
        """Parse NDJSON stream-json output line by line.

        Each line is a JSON object. We detect:
        - text_delta events -> call on_text_delta
        - tool_use content_block_start -> call on_tool_progress
        - AskUserQuestion tool_use -> call on_question
        - message_start -> extract model
        - result type -> extract session_id

        Args:
            stdout: Process stdout stream.
            state: Mutable stream state.
            on_text_delta: Text delta callback.
            on_tool_progress: Tool progress callback.
            on_question: Question callback.
        """
        async for raw_line in stdout:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line:
                continue

            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                await logger.adebug("claude_code_unparseable_line", line=line[:200])
                continue

            await self._handle_event(
                event=event,
                state=state,
                on_text_delta=on_text_delta,
                on_tool_progress=on_tool_progress,
                on_question=on_question,
            )

    async def _handle_event(
        self,
        *,
        event: dict[str, object],
        state: _StreamState,
        on_text_delta: TextDeltaCallback | None,
        on_tool_progress: ToolProgressCallback | None,
        on_question: QuestionCallback | None,
    ) -> None:
        """Handle a single parsed JSON event from stream-json.

        Args:
            event: Parsed JSON event dict.
            state: Mutable stream state.
            on_text_delta: Text delta callback.
            on_tool_progress: Tool progress callback.
            on_question: Question callback.
        """
        event_type = event.get("type")

        # --- Result event (json format output) ---
        if event_type == "result":
            result_text = event.get("result")
            if isinstance(result_text, str) and result_text:
                state.full_text = result_text
            sid = event.get("session_id")
            if isinstance(sid, str):
                state.session_id = sid
            return

        # --- Stream events ---
        if event_type != "stream_event":
            return

        inner = event.get("event")
        if not isinstance(inner, dict):
            return

        inner_type = inner.get("type")

        # message_start: extract model and session info, transition to thinking
        if inner_type == "message_start":
            message = inner.get("message")
            if isinstance(message, dict):
                model = message.get("model")
                if isinstance(model, str):
                    state.model = model
            state.phase = "thinking"
            state.stream_started_at = time.monotonic()
            if on_tool_progress is not None:
                await on_tool_progress(self._build_progress_event(state))

        # content_block_start: detect tool_use or text block
        elif inner_type == "content_block_start":
            content_block = inner.get("content_block")
            if isinstance(content_block, dict):
                block_type = content_block.get("type")
                if block_type == "tool_use":
                    tool_name = content_block.get("name", "")
                    if isinstance(tool_name, str):
                        state.current_tool_name = tool_name
                        state.current_tool_input_json = ""
                        state.is_collecting_tool_input = True

                        if tool_name != "AskUserQuestion":
                            state.phase = "tool_calling"
                            state.tool_executions.append(
                                _ToolExecution(
                                    tool_name=tool_name,
                                    started_at=time.monotonic(),
                                )
                            )
                            if on_tool_progress is not None:
                                await on_tool_progress(self._build_progress_event(state))

        # content_block_delta: text tokens or tool input JSON fragments
        elif inner_type == "content_block_delta":
            delta = inner.get("delta")
            if not isinstance(delta, dict):
                return

            delta_type = delta.get("type")

            # Text delta -> append and callback
            if delta_type == "text_delta":
                text = delta.get("text", "")
                if isinstance(text, str) and text:
                    # Transition to generating phase on first text after tools
                    if state.phase == "tool_calling" and not state.is_collecting_tool_input:
                        state.phase = "generating"
                        if on_tool_progress is not None:
                            await on_tool_progress(self._build_progress_event(state))
                    state.full_text += text
                    if on_text_delta is not None:
                        await on_text_delta(text, state.delta_index)
                    state.delta_index += 1

            # Tool input JSON delta -> accumulate
            elif delta_type == "input_json_delta":
                partial = delta.get("partial_json", "")
                if isinstance(partial, str) and state.is_collecting_tool_input:
                    state.current_tool_input_json += partial

        # content_block_stop: finalize tool input, handle AskUserQuestion
        elif inner_type == "content_block_stop":
            if state.is_collecting_tool_input:
                state.is_collecting_tool_input = False

                if state.current_tool_name == "AskUserQuestion":
                    await self._handle_ask_user_question(
                        state=state,
                        on_question=on_question,
                    )
                else:
                    # Mark tool as completed with timing
                    for tex in reversed(state.tool_executions):
                        if tex.status == "active" and tex.tool_name == state.current_tool_name:
                            tex.completed_at = time.monotonic()
                            tex.status = "completed"
                            break
                    if on_tool_progress is not None:
                        await on_tool_progress(self._build_progress_event(state))

                state.current_tool_name = ""
                state.current_tool_input_json = ""

    async def _handle_ask_user_question(
        self,
        *,
        state: _StreamState,
        on_question: QuestionCallback | None,
    ) -> None:
        """Handle AskUserQuestion tool call from claude -p.

        Parses the accumulated tool input JSON, extracts question details,
        and calls the question callback to get the user's answer.

        Args:
            state: Stream state with accumulated tool input.
            on_question: Callback that sends question to iOS and waits for answer.
        """
        if on_question is None:
            return

        try:
            question_input = json.loads(state.current_tool_input_json)
        except json.JSONDecodeError:
            await logger.awarning(
                "claude_code_invalid_question_json",
                raw=state.current_tool_input_json[:500],
            )
            return

        await logger.ainfo(
            "claude_code_question_detected",
            question=str(question_input.get("question", ""))[:100],
        )

        await on_question(question_input)

    @staticmethod
    async def _record_rate_limit() -> None:
        """Record a rate limit event in the subscription usage service."""
        try:
            from app.services.subscription_usage_service import (
                subscription_usage_service,
            )

            await subscription_usage_service.record_rate_limit()
        except Exception:
            await logger.awarning("rate_limit_record_failed")
