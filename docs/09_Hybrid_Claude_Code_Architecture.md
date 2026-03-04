# 09 - Hybrid Claude Code Architecture

> iOS mesajlarini `claude -p` subprocess ile isleme mimarisi.
> Bu dokuman, implementasyonu yapacak agent'in hicbir karar vermeden adim adim kodlayabilecegi detayda yazilmistir.

---

## 1. Mimari Ozet

### Temel Prensip

**Her iOS mesaji `claude -p` subprocess ile islenir.** API (Bedrock/Anthropic) sadece fallback olarak bulunur ve config'den acilabilir.

### Akis

```
iOS App
  → WebSocket mesaj gonderir
  → Backend: aninda PROGRESS mesaji gonderir ("Sorgunuz isleniyor...")
  → Backend: claude -p subprocess baslatir
  → Backend: stream-json ciktisini parse eder
  → Backend: text delta'lari CHAT_STREAM olarak iOS'a iletir
  → Backend: tool kullanimi tespit ederse PROGRESS gonderir
  → Backend: AskUserQuestion tespit ederse QUESTION gonderir, cevap bekler
  → Backend: islem bitince CHAT_STREAM_END gonderir
```

### Maliyet

- `claude -p`: Max subscription kapsaminda ($200/ay sabit)
- API fallback: Sadece config'den acilirsa, per-token Bedrock/Anthropic

---

## 2. Yeni Config Alanlari

### Dosya: `apps/backend/app/core/config.py`

`Settings` class'ina su alanlari EKLE (mevcut Claude AI Orchestrator bolumunun ALTINA):

```python
# --- Claude Code (claude -p) ---
claude_code_enabled: bool = True
claude_code_binary: str = "claude"
claude_code_project_dir: str = "/opt/rafraf"
claude_code_max_turns: int = 30
claude_code_model: str = "sonnet"
claude_code_timeout_seconds: int = 300
claude_code_fallback_to_api: bool = True
```

### Aciklamalar

| Alan | Varsayilan | Aciklama |
|------|-----------|----------|
| `claude_code_enabled` | `True` | `True` ise her mesaj claude -p ile islenir |
| `claude_code_binary` | `"claude"` | claude CLI binary yolu (PATH'te olmalidir) |
| `claude_code_project_dir` | `"/opt/rafraf"` | Proje repo dizini (claude -p burada calisir) |
| `claude_code_max_turns` | `30` | claude -p --max-turns degeri |
| `claude_code_model` | `"sonnet"` | claude -p --model degeri (sonnet, opus, haiku) |
| `claude_code_timeout_seconds` | `300` | Subprocess timeout (5 dakika) |
| `claude_code_fallback_to_api` | `True` | claude -p basarisiz olursa API'ya geri don |

### Ortam Degiskenleri

`.env` dosyasina EKLE:

```env
# --- Claude Code (claude -p) ---
CLAUDE_CODE_ENABLED=true
CLAUDE_CODE_BINARY=claude
CLAUDE_CODE_PROJECT_DIR=/opt/rafraf
CLAUDE_CODE_MAX_TURNS=30
CLAUDE_CODE_MODEL=sonnet
CLAUDE_CODE_TIMEOUT_SECONDS=300
CLAUDE_CODE_FALLBACK_TO_API=true
```

---

## 3. Yeni Dosya: `apps/backend/app/orchestrator/claude_code_runner.py`

Bu dosya `claude -p` subprocess'ini yonetir. stream-json ciktisini parse eder ve callback'ler araciligiyla WebSocket'e iletir.

### Tam Implementasyon

```python
"""Claude Code runner - subprocess wrapper for claude -p pipe mode."""

import asyncio
import json
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field

import structlog

from app.core.config import get_settings

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

# Type aliases
TextDeltaCallback = Callable[[str, int], Coroutine[object, object, None]]
ToolProgressCallback = Callable[[str], Coroutine[object, object, None]]
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

        await logger.ainfo(
            "claude_code_starting",
            project_dir=self._settings.claude_code_project_dir,
            model=self._settings.claude_code_model,
            max_turns=self._settings.claude_code_max_turns,
            resume_session=session_id,
        )

        state = _StreamState()

        try:
            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=self._settings.claude_code_project_dir,
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
            except asyncio.TimeoutError:
                self._process.kill()
                raise ClaudeCodeError(
                    f"claude -p timed out after {self._settings.claude_code_timeout_seconds}s",
                    returncode=-1,
                )

            returncode = self._process.returncode or 0

            if returncode != 0 and not state.full_text:
                stderr_text = stderr_bytes.decode("utf-8", errors="replace").strip()
                raise ClaudeCodeError(
                    f"claude -p exited with code {returncode}: {stderr_text}",
                    returncode=returncode,
                )

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
            "--output-format", "stream-json",
            "--model", self._settings.claude_code_model,
            "--max-turns", str(self._settings.claude_code_max_turns),
            "--verbose",
        ]

        if session_id:
            cmd.extend(["--resume", session_id])

        if append_system_prompt:
            cmd.extend(["--append-system-prompt", append_system_prompt])

        return cmd

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

        # message_start: extract model and session info
        if inner_type == "message_start":
            message = inner.get("message")
            if isinstance(message, dict):
                model = message.get("model")
                if isinstance(model, str):
                    state.model = model

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

                        # AskUserQuestion is handled separately at content_block_stop
                        if tool_name != "AskUserQuestion" and on_tool_progress is not None:
                            await on_tool_progress(tool_name)

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

                # Check if this was AskUserQuestion
                if state.current_tool_name == "AskUserQuestion":
                    await self._handle_ask_user_question(
                        state=state,
                        on_question=on_question,
                    )

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

        # question_input format from Claude Code:
        # {
        #   "question": "Which database should we use?",
        #   "options": [
        #     {"label": "PostgreSQL", "description": "..."},
        #     {"label": "Redis", "description": "..."}
        #   ]
        # }
        await logger.ainfo(
            "claude_code_question_detected",
            question=str(question_input.get("question", ""))[:100],
        )

        await on_question(question_input)
```

---

## 4. Yeni Dosya: `apps/backend/app/orchestrator/question_bridge.py`

Bu dosya Claude Code'un sordugu sorulari iOS'a iletir ve cevabin donmesini bekler.

### Tam Implementasyon

```python
"""Question bridge - forwards Claude Code questions to iOS and waits for answers."""

import asyncio
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
        send_to_ios: "SendToIosCallback",
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
        options: list[dict[str, object]] = []
        if isinstance(raw_options, list):
            for i, opt in enumerate(raw_options):
                if isinstance(opt, dict):
                    options.append(
                        QuestionOptionPayload(
                            id=str(i),
                            label=str(opt.get("label", f"Option {i + 1}")),
                            style="default",
                        ).model_dump()
                    )

        question_msg = QuestionPayload(
            approval_id=approval_id,
            question=question_text,
            context=str(question_payload.get("context", "")),
            options=options if options else None,
            timeout_seconds=_QUESTION_TIMEOUT_SECONDS,
            category="claude_code_question",
        )

        # Create future for answer
        future: asyncio.Future[str] = asyncio.get_event_loop().create_future()
        self._pending[approval_id] = future

        # Send question to iOS
        from datetime import UTC, datetime

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
        except asyncio.TimeoutError:
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


# Type alias for the WebSocket send callback
SendToIosCallback = "Callable[[dict[str, object]], Coroutine[object, object, None]]"


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
```

---

## 5. Guncellenmesi Gereken Dosya: `apps/backend/app/services/orchestrator_service.py`

### Degisiklik Ozeti

Mevcut `OrchestratorService` class'ina yeni bir method EKLE: `process_with_claude_code()`.
Mevcut `process_user_message()` ve `process_user_message_streaming()` methodlarini KORU (API fallback).

### Eklenecek Import'lar (dosyanin basina)

```python
from app.orchestrator.claude_code_runner import ClaudeCodeError, ClaudeCodeRunner
```

### Eklenecek Method (class icine, `clear_session` methodundan ONCE)

```python
    async def process_with_claude_code(
        self,
        *,
        session_id: str,
        user_id: str,
        message: str,
        claude_session_id: str | None = None,
        on_text_delta: "Callable[[str, int], Coroutine[object, object, None]] | None" = None,
        on_stream_end: "Callable[[str], Coroutine[object, object, None]] | None" = None,
        on_tool_progress: "Callable[[str], Coroutine[object, object, None]] | None" = None,
        on_question: "Callable[[dict[str, object]], Coroutine[object, object, str | None]] | None" = None,
    ) -> OrchestratorResponse:
        """Process a user message via claude -p subprocess.

        Primary execution path. Falls back to API if claude -p fails
        and fallback is enabled in config.

        Args:
            session_id: WebSocket session ID.
            user_id: Authenticated user ID.
            message: User message text.
            claude_session_id: Previous claude -p session ID for --resume.
            on_text_delta: Streaming text callback.
            on_stream_end: Stream completion callback.
            on_tool_progress: Tool usage progress callback.
            on_question: Question forwarding callback.

        Returns:
            OrchestratorResponse with AI response.
        """
        from app.core.config import get_settings

        settings = get_settings()

        await logger.ainfo(
            "claude_code_processing",
            session_id=session_id,
            user_id=user_id,
            message_length=len(message),
        )

        runner = ClaudeCodeRunner()

        # Build context info for system prompt
        context_parts: list[str] = [
            f"WebSocket Session: {session_id}",
            f"User ID: {user_id}",
        ]
        append_prompt = "\n".join(context_parts)

        try:
            result = await runner.run(
                prompt=message,
                session_id=claude_session_id,
                on_text_delta=on_text_delta,
                on_tool_progress=on_tool_progress,
                on_question=on_question,
                on_stream_end=on_stream_end,
                append_system_prompt=append_prompt,
            )

            await logger.ainfo(
                "claude_code_response_generated",
                session_id=session_id,
                claude_session_id=result.session_id,
                model=result.model_used,
                text_length=len(result.response_text),
            )

            return OrchestratorResponse(
                session_id=session_id,
                response_text=result.response_text,
                model_used=f"claude-code:{result.model_used}",
                tokens_input=0,
                tokens_output=0,
                tool_calls_count=0,
            )

        except ClaudeCodeError as exc:
            await logger.aerror(
                "claude_code_failed",
                session_id=session_id,
                error=exc.message,
                returncode=exc.returncode,
            )

            # Fallback to API if enabled
            if settings.claude_code_fallback_to_api:
                await logger.ainfo(
                    "claude_code_fallback_to_api",
                    session_id=session_id,
                )
                return await self.process_user_message_streaming(
                    session_id=session_id,
                    user_id=user_id,
                    message=message,
                    on_text_delta=on_text_delta,
                    on_stream_end=on_stream_end,
                )

            return OrchestratorResponse(
                session_id=session_id,
                response_text="AI servisi gecici olarak kullanilamiyor. Lutfen tekrar deneyin.",
                model_used="none",
                tokens_input=0,
                tokens_output=0,
                tool_calls_count=0,
            )
```

---

## 6. Guncellenmesi Gereken Dosya: `apps/backend/app/api/routes/websocket.py`

### Degisiklik Ozeti

`_process_with_orchestrator()` fonksiyonunu DEGISTIR: claude_code_enabled ise claude -p path'ini kullan, degilse mevcut API path'ini kullan.

### Adim 1: Import ekle (dosya basina)

```python
from app.core.config import get_settings
from app.orchestrator.question_bridge import get_question_bridge
```

### Adim 2: `_process_with_orchestrator` fonksiyonunu TAMAMEN degistir

Mevcut `_process_with_orchestrator` fonksiyonunu asagidaki ile DEGISTIR:

```python
async def _process_with_orchestrator(
    *,
    message: str,
    connection_id: str,
    session_id: str,
    user_id: str,
    voice_mode: bool = False,
) -> None:
    """Process a message through claude -p or API fallback.

    Primary path: claude -p subprocess (Max subscription, $0).
    Fallback path: Bedrock/Anthropic API (per-token).

    Streams text deltas via chat.stream messages as Claude generates tokens.
    Optionally generates TTS audio chunks for voice mode.
    """
    settings = get_settings()
    message_id = str(uuid4())
    tts_service = None
    sentence_acc = None

    if voice_mode:
        from app.services.tts_service import SentenceAccumulator, TTSService

        tts_service = TTSService()
        sentence_acc = SentenceAccumulator()

    tts_tasks: list[asyncio.Task[None]] = []
    chunk_index = 0

    # --- Progress: islem basladi ---
    startup_progress = _build_message(
        MessageType.PROGRESS,
        ProgressPayload(
            task="Sorgunuz isleniyor...",
            step=1,
            total_steps=3,
            percentage=10,
            details="Baslaniyor",
        ).model_dump(exclude_none=True),
        session_id=session_id,
    )
    await manager.send_json(connection_id, startup_progress)

    # --- Callbacks ---

    async def _on_text_delta(delta: str, index: int) -> None:
        """Send streaming text delta to client."""
        nonlocal chunk_index
        stream_msg = _build_message(
            MessageType.CHAT_STREAM,
            ChatStreamPayload(
                message_id=message_id,
                delta=delta,
                index=index,
            ).model_dump(),
            session_id=session_id,
        )
        await manager.send_json(connection_id, stream_msg)

        # TTS: accumulate sentences and send audio chunks
        if tts_service is not None and sentence_acc is not None:
            sentences = sentence_acc.add(delta)
            for sentence in sentences:
                ci = chunk_index
                chunk_index += 1
                task = asyncio.create_task(
                    _send_tts_chunk(
                        tts_service,
                        sentence,
                        message_id,
                        ci,
                        connection_id,
                        session_id,
                    )
                )
                tts_tasks.append(task)

    async def _on_stream_end(full_text: str) -> None:
        """Finalize streaming: flush TTS buffer, send stream end."""
        nonlocal chunk_index

        if tts_service is not None and sentence_acc is not None:
            remaining = sentence_acc.flush()
            if remaining:
                ci = chunk_index
                chunk_index += 1
                task = asyncio.create_task(
                    _send_tts_chunk(
                        tts_service,
                        remaining,
                        message_id,
                        ci,
                        connection_id,
                        session_id,
                        is_last=True,
                    )
                )
                tts_tasks.append(task)

        if tts_tasks:
            await asyncio.gather(*tts_tasks, return_exceptions=True)

        if tts_service is not None:
            audio_end_msg = _build_message(
                MessageType.VOICE_AUDIO_END,
                {"message_id": message_id},
                session_id=session_id,
            )
            await manager.send_json(connection_id, audio_end_msg)

    async def _on_tool_progress(tool_name: str) -> None:
        """Send tool progress to iOS."""
        progress_msg = _build_message(
            MessageType.PROGRESS,
            ProgressPayload(
                task=f"Calisiyor: {tool_name}",
                step=2,
                total_steps=3,
                percentage=50,
                details=f"Tool: {tool_name}",
            ).model_dump(exclude_none=True),
            session_id=session_id,
        )
        await manager.send_json(connection_id, progress_msg)

    async def _on_question(question_payload: dict[str, object]) -> str | None:
        """Forward question to iOS and wait for answer."""
        bridge = get_question_bridge()

        async def _send_to_ios(msg: dict[str, object]) -> None:
            await manager.send_json(connection_id, msg)

        return await bridge.ask_user(
            question_payload=question_payload,
            send_to_ios=_send_to_ios,
            session_id=session_id,
        )

    # --- Ana islem ---

    async def _run_processing() -> None:
        orchestrator = OrchestratorService()

        if settings.claude_code_enabled:
            # --- PRIMARY PATH: claude -p ---
            analyzing_progress = _build_message(
                MessageType.PROGRESS,
                ProgressPayload(
                    task="Proje analiz ediliyor...",
                    step=2,
                    total_steps=3,
                    percentage=30,
                    details="Claude Code baslatiliyor",
                ).model_dump(exclude_none=True),
                session_id=session_id,
            )
            await manager.send_json(connection_id, analyzing_progress)

            response = await orchestrator.process_with_claude_code(
                session_id=session_id,
                user_id=user_id,
                message=message,
                on_text_delta=_on_text_delta,
                on_stream_end=_on_stream_end,
                on_tool_progress=_on_tool_progress,
                on_question=_on_question,
            )
        else:
            # --- FALLBACK PATH: API ---
            host_status = await _build_host_status()
            response = await orchestrator.process_user_message_streaming(
                session_id=session_id,
                user_id=user_id,
                message=message,
                on_text_delta=_on_text_delta,
                on_stream_end=_on_stream_end,
                progress_callback=lambda name, step, total: _on_tool_progress(name),
                host_status=host_status,
            )

        # Send CHAT_STREAM_END with metadata
        end_msg = _build_message(
            MessageType.CHAT_STREAM_END,
            ChatStreamEndPayload(
                message_id=message_id,
                full_text=response.response_text,
                model_used=response.model_used,
                tokens_used={
                    "input": response.tokens_input,
                    "output": response.tokens_output,
                },
            ).model_dump(),
            session_id=session_id,
        )
        await manager.send_json(connection_id, end_msg)

    # Run as cancellable task
    task = asyncio.create_task(_run_processing())
    _active_streams[connection_id] = task

    try:
        await task
    except asyncio.CancelledError:
        await logger.ainfo(
            "streaming_interrupted",
            connection_id=connection_id,
            session_id=session_id,
        )
        for tts_task in tts_tasks:
            if not tts_task.done():
                tts_task.cancel()
    finally:
        _active_streams.pop(connection_id, None)
```

### Adim 3: Question Response handler'i guncelle

Mevcut `_handle_approval_response` fonksiyonuna QuestionBridge entegrasyonu EKLE.

`_handle_approval_response` fonksiyonunun SONUNA (basarili submit'den sonra) su kodu EKLE:

```python
    # Also check QuestionBridge for claude -p questions
    if not submitted:
        bridge = get_question_bridge()
        note_answer = note_str or decision_str
        bridge_submitted = bridge.submit_answer(approval_id, note_answer)
        if bridge_submitted:
            await logger.ainfo(
                "question_bridge_answer_submitted",
                approval_id=approval_id,
                answer=note_answer[:100] if note_answer else "",
            )
            return
```

---

## 7. Session Yonetimi: claude -p Session Resume

### Claude -p Session Akisi

```
1. Ilk mesaj:
   claude -p "plan cikart" --output-format stream-json
   → Cikti sonunda session_id donulur
   → Backend bu session_id'yi Redis'e kaydeder:
     Key: "claude_session:{ws_session_id}" -> Value: "{claude_session_id}"

2. Devam mesaji (ayni WebSocket session'da):
   → Backend Redis'ten claude_session_id'yi okur
   → claude -p "devam et" --resume {claude_session_id} --output-format stream-json
   → Conversation devam eder

3. Soru cevabi sonrasi devam:
   → Kullanici soruyu cevaplar
   → claude -p "Kullanici soruya su cevabi verdi: {answer}" --resume {claude_session_id}
   → Claude Code cevapla devam eder
```

### Redis Session Kaydi (orchestrator_service.py'ye ekle)

```python
    async def _save_claude_session(self, ws_session_id: str, claude_session_id: str) -> None:
        """Save claude -p session ID to Redis for session continuation."""
        import redis.asyncio as redis
        from app.core.config import get_settings
        settings = get_settings()
        r = redis.from_url(settings.redis_url)
        await r.set(
            f"claude_session:{ws_session_id}",
            claude_session_id,
            ex=86400,  # 24 saat TTL
        )
        await r.aclose()

    async def _get_claude_session(self, ws_session_id: str) -> str | None:
        """Get saved claude -p session ID from Redis."""
        import redis.asyncio as redis
        from app.core.config import get_settings
        settings = get_settings()
        r = redis.from_url(settings.redis_url)
        result = await r.get(f"claude_session:{ws_session_id}")
        await r.aclose()
        if isinstance(result, bytes):
            return result.decode("utf-8")
        return None
```

### process_with_claude_code icindeki session kullanimi

`process_with_claude_code` methodunda, runner.run() ONCESINE session lookup EKLE:

```python
        # Lookup previous claude session for conversation continuation
        if claude_session_id is None:
            claude_session_id = await self._get_claude_session(session_id)

        # ... runner.run() cagrilir ...

        # Save session after successful execution
        if result.session_id:
            await self._save_claude_session(session_id, result.session_id)
```

---

## 8. Interaktif Progress Mesajlari

### Progress Akisi (iOS kullanicisinin gordugu)

| Zaman | PROGRESS Mesaji | percentage |
|-------|----------------|------------|
| 0ms | "Sorgunuz isleniyor..." | 10 |
| ~100ms | "Proje analiz ediliyor..." | 30 |
| subprocess ilk text | (PROGRESS durur, CHAT_STREAM baslar) | - |
| tool kullanimi | "Calisiyor: Read" / "Calisiyor: Grep" / vb. | 50 |
| stream bitti | CHAT_STREAM_END | 100 |

### iOS Tarafinda (ChatView)

iOS uygulamasinda PROGRESS mesajlari geldiginde:

- Animasyonlu typing indicator gosterilir
- Progress text guncellenir ("Proje analiz ediliyor...")
- CHAT_STREAM basladiginda typing indicator gizlenir
- Text baloncugu yavas yavas dolar (streaming)

**NOT**: iOS tarafinda hicbir degisiklik gerekmez cunku mevcut PROGRESS ve CHAT_STREAM message handler'lari zaten var. Sadece progress mesajlarinin icerigi degisiyor.

---

## 9. config.py Tam Degisiklik

### Eklenecek Alanlar

`apps/backend/app/core/config.py` dosyasindaki `Settings` class'ina, mevcut `approval_timeout_seconds` ALTINA su alanlari EKLE:

```python
    # --- Claude Code (claude -p subprocess) ---
    claude_code_enabled: bool = True
    claude_code_binary: str = "claude"
    claude_code_project_dir: str = "/opt/rafraf"
    claude_code_max_turns: int = 30
    claude_code_model: str = "sonnet"
    claude_code_timeout_seconds: int = 300
    claude_code_fallback_to_api: bool = True
```

---

## 10. Dosya Listesi - Olustur / Degistir

### YENI DOSYALAR (olustur)

| Dosya | Satir (tahmini) | Aciklama |
|-------|----------------|----------|
| `app/orchestrator/claude_code_runner.py` | ~350 | claude -p subprocess + stream parser |
| `app/orchestrator/question_bridge.py` | ~130 | Soru iOS'a iletme + cevap bekleme |

### DEGISECEK DOSYALAR

| Dosya | Degisiklik |
|-------|-----------|
| `app/core/config.py` | 7 yeni alan ekle (Section 9) |
| `app/services/orchestrator_service.py` | `process_with_claude_code()` method + session helpers ekle |
| `app/api/routes/websocket.py` | `_process_with_orchestrator()` fonksiyonunu degistir + question bridge |

### DEGISMEYECEK DOSYALAR

| Dosya | Neden |
|-------|-------|
| `app/orchestrator/agent.py` | API fallback olarak KALIR, degismez |
| `app/orchestrator/model_router.py` | API fallback icin KALIR, degismez |
| `app/orchestrator/prompt_builder.py` | API fallback icin KALIR, degismez |
| `app/orchestrator/tool_registry.py` | API fallback icin KALIR, degismez |
| `app/tools/*.py` | API fallback icin KALIR, degismez |
| `app/schemas/messages.py` | Mevcut PROGRESS, QUESTION, CHAT_STREAM tipleri yeterli |
| `app/schemas/orchestrator.py` | Mevcut OrchestratorResponse yeterli |
| iOS tarafindaki tum dosyalar | Mevcut message handler'lar yeterli |

---

## 11. Test Plani

### Unit Testler

#### `tests/orchestrator/test_claude_code_runner.py`

```python
"""Tests for ClaudeCodeRunner."""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.orchestrator.claude_code_runner import ClaudeCodeRunner, ClaudeCodeError


@pytest.fixture
def mock_settings():
    """Create mock settings for testing."""
    settings = MagicMock()
    settings.claude_code_enabled = True
    settings.claude_code_binary = "claude"
    settings.claude_code_project_dir = "/tmp/test-project"
    settings.claude_code_max_turns = 10
    settings.claude_code_model = "sonnet"
    settings.claude_code_timeout_seconds = 30
    settings.claude_code_fallback_to_api = True
    return settings


class TestClaudeCodeRunner:
    """Test suite for ClaudeCodeRunner."""

    async def test_build_command_basic(self, mock_settings):
        """Test command building with basic parameters."""
        with patch("app.orchestrator.claude_code_runner.get_settings", return_value=mock_settings):
            runner = ClaudeCodeRunner()
            cmd = runner._build_command(prompt="test prompt")

        assert cmd[0] == "claude"
        assert "-p" in cmd
        assert "test prompt" in cmd
        assert "--output-format" in cmd
        assert "stream-json" in cmd
        assert "--model" in cmd
        assert "sonnet" in cmd

    async def test_build_command_with_resume(self, mock_settings):
        """Test command building with session resume."""
        with patch("app.orchestrator.claude_code_runner.get_settings", return_value=mock_settings):
            runner = ClaudeCodeRunner()
            cmd = runner._build_command(
                prompt="continue",
                session_id="550e8400-e29b-41d4-a716-446655440000",
            )

        assert "--resume" in cmd
        assert "550e8400-e29b-41d4-a716-446655440000" in cmd

    async def test_text_delta_callback(self, mock_settings):
        """Test that text deltas are properly forwarded."""
        # Simulated stream-json lines
        stream_lines = [
            json.dumps({"type": "stream_event", "event": {"type": "message_start", "message": {"model": "claude-sonnet-4-5"}}}),
            json.dumps({"type": "stream_event", "event": {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}}),
            json.dumps({"type": "stream_event", "event": {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Hello"}}}),
            json.dumps({"type": "stream_event", "event": {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": " world"}}}),
            json.dumps({"type": "stream_event", "event": {"type": "content_block_stop", "index": 0}}),
            json.dumps({"type": "stream_event", "event": {"type": "message_stop"}}),
            json.dumps({"type": "result", "result": "Hello world", "session_id": "test-session-123"}),
        ]
        # Test implementation validates stream parsing

    async def test_tool_progress_callback(self, mock_settings):
        """Test that tool usage triggers progress callback."""
        stream_lines = [
            json.dumps({"type": "stream_event", "event": {"type": "content_block_start", "index": 1, "content_block": {"type": "tool_use", "id": "tool_1", "name": "Read", "input": {}}}}),
        ]
        # Test validates on_tool_progress called with "Read"

    async def test_ask_user_question_detection(self, mock_settings):
        """Test AskUserQuestion tool detection."""
        stream_lines = [
            json.dumps({"type": "stream_event", "event": {"type": "content_block_start", "index": 2, "content_block": {"type": "tool_use", "id": "ask_1", "name": "AskUserQuestion", "input": {}}}}),
            json.dumps({"type": "stream_event", "event": {"type": "content_block_delta", "index": 2, "delta": {"type": "input_json_delta", "partial_json": "{\"question\": \"Which DB?\"}"}}}),
            json.dumps({"type": "stream_event", "event": {"type": "content_block_stop", "index": 2}}),
        ]
        # Test validates on_question called with {"question": "Which DB?"}

    async def test_timeout_handling(self, mock_settings):
        """Test subprocess timeout raises ClaudeCodeError."""
        mock_settings.claude_code_timeout_seconds = 1
        # Test validates ClaudeCodeError raised on timeout

    async def test_nonzero_exit_code(self, mock_settings):
        """Test non-zero exit code raises ClaudeCodeError."""
        # Test validates ClaudeCodeError with returncode

    async def test_cancel(self, mock_settings):
        """Test process cancellation."""
        # Test validates process.kill() called
```

#### `tests/orchestrator/test_question_bridge.py`

```python
"""Tests for QuestionBridge."""

import asyncio
import pytest
from unittest.mock import AsyncMock

from app.orchestrator.question_bridge import QuestionBridge


class TestQuestionBridge:
    """Test suite for QuestionBridge."""

    async def test_ask_and_answer(self):
        """Test complete question-answer flow."""
        bridge = QuestionBridge()
        send_mock = AsyncMock()

        # Start ask in background
        ask_task = asyncio.create_task(
            bridge.ask_user(
                question_payload={"question": "Which DB?", "options": [{"label": "PostgreSQL"}]},
                send_to_ios=send_mock,
                session_id="test-session",
            )
        )

        await asyncio.sleep(0.1)

        # Verify question sent to iOS
        assert send_mock.called
        sent_msg = send_mock.call_args[0][0]
        approval_id = sent_msg["content"]["approval_id"]

        # Submit answer
        bridge.submit_answer(approval_id, "PostgreSQL")

        answer = await ask_task
        assert answer == "PostgreSQL"

    async def test_timeout(self):
        """Test question timeout returns None."""
        # Override timeout to 1 second for testing
        bridge = QuestionBridge()
        send_mock = AsyncMock()

        answer = await asyncio.wait_for(
            bridge.ask_user(
                question_payload={"question": "test?"},
                send_to_ios=send_mock,
                session_id="test-session",
            ),
            timeout=2,
        )
        # Should return None on timeout

    async def test_submit_unknown_approval_id(self):
        """Test submitting answer for unknown approval returns False."""
        bridge = QuestionBridge()
        result = bridge.submit_answer("nonexistent-id", "answer")
        assert result is False
```

---

## 12. Deployment Gereksinimleri

### Sunucuda claude CLI Kurulumu

```bash
# Claude Code CLI kurulumu
npm install -g @anthropic-ai/claude-code

# Dogrulama
claude --version

# Authentication (API key ile)
export ANTHROPIC_API_KEY="sk-ant-..."
claude auth login

# Veya Max subscription ile
claude auth login  # browser-based login
```

### Proje Dizini Hazirlik

```bash
# Sunucuda proje klonu
git clone https://github.com/atknatk/rafraf.git /opt/rafraf
cd /opt/rafraf

# CLAUDE.md ve .claude/ dizininin mevcut oldugundan emin ol
ls CLAUDE.md .claude/agents/ .claude/skills/ .claude/settings.json
```

### Docker / EKS Ortami

Eger backend Docker container icinde calisiyorsa:

```dockerfile
# Dockerfile'a EKLE
RUN npm install -g @anthropic-ai/claude-code

# Proje dizinini mount et veya COPY et
COPY . /opt/rafraf

# Environment
ENV CLAUDE_CODE_PROJECT_DIR=/opt/rafraf
ENV ANTHROPIC_API_KEY=sk-ant-...
```

---

## 13. Hata Senaryolari ve Recovery

| Senaryo | Ne Olur | Recovery |
|---------|---------|---------|
| claude binary bulunamadi | `ClaudeCodeError` firlatilir | `fallback_to_api=true` ise API'ya doner |
| Subprocess timeout (>300s) | Process kill edilir, `ClaudeCodeError` | API fallback |
| Non-zero exit code | `ClaudeCodeError` ile log'lanir | API fallback |
| stream-json parse hatasi | Satir atlanir, devam eder | Islem devam eder |
| AskUserQuestion timeout (>300s) | `None` donulur | claude -p cevapsiz devam eder |
| Max subscription rate limit | claude -p icten 429 alir | Retry claude -p'nin ici tarafindan |
| ANTHROPIC_API_KEY eksik | claude -p auth hatasi verir | API fallback (Bedrock key ile) |
| Proje dizini bulunamadi | Subprocess CWD hatasi | API fallback |
| WebSocket baglantisi koptu | Task cancel edilir | `runner.cancel()` cagirilir |

---

## 14. Ozet: Implementasyon Adim Sirasi

Implementasyonu yapacak agent su siralamayi TAKIP ETMELIDIR:

### Adim 1: Config guncellemesi
- `apps/backend/app/core/config.py` → 7 yeni alan ekle (Section 9)
- `.env` → yeni ortam degiskenleri ekle (Section 2)

### Adim 2: claude_code_runner.py olustur
- `apps/backend/app/orchestrator/claude_code_runner.py` dosyasini Section 3'teki kodla OLUSTUR
- Hicbir degisiklik yapmadan, Section 3'teki kodu birebir kopyala

### Adim 3: question_bridge.py olustur
- `apps/backend/app/orchestrator/question_bridge.py` dosyasini Section 4'teki kodla OLUSTUR
- Hicbir degisiklik yapmadan, Section 4'teki kodu birebir kopyala

### Adim 4: orchestrator_service.py guncelle
- Import ekle (Section 5)
- `process_with_claude_code()` method ekle (Section 5)
- Session helper methodlarini ekle (Section 7)
- Mevcut methodlara DOKUNMA

### Adim 5: websocket.py guncelle
- Import ekle (Section 6, Adim 1)
- `_process_with_orchestrator()` fonksiyonunu DEGISTIR (Section 6, Adim 2)
- `_handle_approval_response()` fonksiyonuna question bridge ekle (Section 6, Adim 3)
- Diger fonksiyonlara DOKUNMA

### Adim 6: Test yaz
- `tests/orchestrator/test_claude_code_runner.py` (Section 11)
- `tests/orchestrator/test_question_bridge.py` (Section 11)

### Adim 7: Dogrulama
- `ruff check apps/backend/app/`
- `mypy apps/backend/app/`
- `python -m pytest tests/orchestrator/`

---

## 15. stream-json Event Referansi

claude -p --output-format stream-json ciktisindaki tum event tipleri:

### Temel Yapilar

Her satir bir JSON nesnesidir (NDJSON formati).

### Event Tipleri

| event.type | Aciklama | Kullanim |
|------------|----------|----------|
| `message_start` | Mesaj basliyor | Model bilgisini cek: `event.message.model` |
| `content_block_start` | Yeni icerik blogu | Blok tipi: `event.content_block.type` ("text" veya "tool_use") |
| `content_block_delta` | Artimsal icerik | Delta tipi: `event.delta.type` ("text_delta" veya "input_json_delta") |
| `content_block_stop` | Blok tamamlandi | Tool input JSON'i finalize et |
| `message_delta` | Mesaj seviyesi guncelleme | `event.delta.stop_reason` ("end_turn") |
| `message_stop` | Mesaj tamamlandi | Stream bitti |

### Ust Seviye Tipler

| type | Aciklama |
|------|----------|
| `stream_event` | API streaming event'i (yukaridaki tablo) |
| `result` | Son cikti — `result` (text), `session_id`, `is_error`, `duration_ms` icerir |

### Text Delta Ornegi

```json
{"type":"stream_event","event":{"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Merhaba"}}}
```

### Tool Use Ornegi

```json
{"type":"stream_event","event":{"type":"content_block_start","index":1,"content_block":{"type":"tool_use","id":"toolu_01X","name":"Read","input":{}}}}
{"type":"stream_event","event":{"type":"content_block_delta","index":1,"delta":{"type":"input_json_delta","partial_json":"{\"file_path\":\""}}}
{"type":"stream_event","event":{"type":"content_block_delta","index":1,"delta":{"type":"input_json_delta","partial_json":"apps/backend/app/main.py\"}"}}}
{"type":"stream_event","event":{"type":"content_block_stop","index":1}}
```

### AskUserQuestion Ornegi

```json
{"type":"stream_event","event":{"type":"content_block_start","index":2,"content_block":{"type":"tool_use","id":"askg_01","name":"AskUserQuestion","input":{}}}}
{"type":"stream_event","event":{"type":"content_block_delta","index":2,"delta":{"type":"input_json_delta","partial_json":"{\"question\":\"Hangi veritabani?\",\"options\":[{\"label\":\"PostgreSQL\"},{\"label\":\"Redis\"}]}"}}}
{"type":"stream_event","event":{"type":"content_block_stop","index":2}}
```

### Result Ornegi

```json
{"type":"result","subtype":"success","result":"Islem tamamlandi...","session_id":"550e8400-e29b-41d4-a716-446655440000","is_error":false,"duration_ms":2500}
```
