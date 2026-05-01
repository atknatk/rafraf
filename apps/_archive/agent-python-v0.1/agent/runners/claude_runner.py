"""Claude Code runner - claude -p subprocess with NDJSON streaming.

Backend'deki ClaudeCodeRunner logigini Agent'a tasir.
BaseRunner'dan extend ETMEZ cunku streaming pattern kullanir (request-response degil).
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import structlog

from agent.core.protocol import (
    ClaudeTaskExecuteContent,
    build_claude_stream_delta_message,
    build_claude_stream_end_message,
    build_claude_stream_error_message,
    build_claude_stream_progress_message,
    build_claude_stream_question_message,
)

if TYPE_CHECKING:
    from agent.core.config import AgentConfig

logger = structlog.get_logger()

SendCallback = Callable[[str], Awaitable[None]]

# -- Tool display names (Turkish) --

_TOOL_DISPLAY_NAMES: dict[str, str] = {
    "Read": "Dosya okunuyor",
    "Write": "Dosya yazılıyor",
    "Edit": "Dosya düzenleniyor",
    "MultiEdit": "Çoklu düzenleme",
    "Bash": "Komut çalıştırılıyor",
    "Glob": "Dosya aranıyor",
    "Grep": "İçerik aranıyor",
    "LS": "Dizin listeleniyor",
    "TodoWrite": "Görev listesi güncelleniyor",
    "WebFetch": "Web sayfası getiriliyor",
    "WebSearch": "Web araması yapılıyor",
    "Agent": "Alt görev çalıştırılıyor",
    "NotebookEdit": "Notebook düzenleniyor",
    "AskUserQuestion": "Kullanıcıya soru soruluyor",
    "SendMessage": "Mesaj gönderiliyor",
}


def _tool_display_name(tool_name: str) -> str:
    """Return Turkish display name for a Claude tool, or raw name as fallback."""
    return _TOOL_DISPLAY_NAMES.get(tool_name, tool_name)


def _tool_input_summary(tool_name: str, input_json: str) -> str | None:
    """Extract a short human-readable summary from a tool's JSON input."""
    if not input_json:
        return None
    try:
        data: dict[str, object] = json.loads(input_json)
    except json.JSONDecodeError:
        return None

    if tool_name in ("Read", "Write", "Edit", "MultiEdit"):
        path = data.get("file_path") or data.get("path")
        if isinstance(path, str):
            parts = path.replace("\\", "/").split("/")
            return "/".join(parts[-2:]) if len(parts) >= 2 else path
    elif tool_name == "Bash":
        cmd = data.get("command", "")
        if isinstance(cmd, str):
            return cmd[:70] + ("…" if len(cmd) > 70 else "")
    elif tool_name == "Glob":
        pattern = data.get("pattern", "")
        if isinstance(pattern, str):
            return pattern
    elif tool_name == "Grep":
        pattern = data.get("pattern", "")
        if isinstance(pattern, str):
            return f'"{pattern}"'
    elif tool_name == "WebFetch":
        url = data.get("url", "")
        if isinstance(url, str):
            return url[:70] + ("…" if len(url) > 70 else "")
    elif tool_name == "WebSearch":
        query = data.get("query", "")
        if isinstance(query, str):
            return query
    elif tool_name == "LS":
        path = data.get("path", "")
        if isinstance(path, str):
            return path
    return None


# -- Internal state tracking --


@dataclass
class _ToolExecution:
    """Tracks a single tool invocation with timing."""

    tool_name: str
    started_at: float
    completed_at: float | None = None
    status: str = "active"
    input_summary: str | None = None


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
    tool_executions: list[_ToolExecution] = field(default_factory=list)
    phase: str = "starting"
    stream_started_at: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0


class ClaudeRunner:
    """Runs claude -p as an async subprocess on the host machine.

    Parses NDJSON output and streams results back to the backend
    via WebSocket messages (claude_stream_delta, claude_stream_progress, etc.).
    """

    def __init__(
        self,
        send_callback: SendCallback,
        host_id: str,
        config: AgentConfig,
    ) -> None:
        self._send = send_callback
        self._host_id = host_id
        self._config = config
        self._active_processes: dict[str, asyncio.subprocess.Process] = {}
        self._pending_answers: dict[str, asyncio.Future[str]] = {}

    async def run(self, content: ClaudeTaskExecuteContent) -> None:
        """Execute claude -p and stream results via WebSocket messages.

        Args:
            content: Parsed claude_task_execute payload.
        """
        task_id = content.task_id

        cmd = self._build_command(content)
        effective_dir = content.project_dir or None

        # Validate project_dir is within allowed scan paths
        if effective_dir is not None:
            from pathlib import Path

            resolved = str(Path(effective_dir).resolve())
            allowed_paths = self._config.project_scan_paths
            if allowed_paths and not any(
                resolved.startswith(str(Path(p).resolve())) for p in allowed_paths
            ):
                await self._send(
                    build_claude_stream_error_message(
                        task_id=task_id,
                        host_id=self._host_id,
                        error=f"project_dir '{effective_dir}' izin verilen dizinlerin disinda.",
                        returncode=-1,
                    ),
                )
                return

        # Strip ANTHROPIC_API_KEY to force Max subscription
        subprocess_env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}

        await logger.ainfo(
            "claude_runner_starting",
            task_id=task_id,
            project_dir=effective_dir,
            model=content.model,
            max_turns=content.max_turns,
            resume_session=content.session_id,
        )

        state = _StreamState()

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=effective_dir,
                env=subprocess_env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self._active_processes[task_id] = process

            assert process.stdout is not None  # noqa: S101
            assert process.stderr is not None  # noqa: S101

            # Parse NDJSON stream
            await self._parse_stream(
                stdout=process.stdout,
                state=state,
                task_id=task_id,
            )

            # Wait for process to finish (stdout already consumed by _parse_stream)
            try:
                stderr_bytes = await process.stderr.read()
                await asyncio.wait_for(
                    process.wait(),
                    timeout=self._config.claude_timeout_seconds,
                )
            except TimeoutError:
                process.kill()
                await self._send(
                    build_claude_stream_error_message(
                        task_id=task_id,
                        host_id=self._host_id,
                        error=f"claude -p timed out after {self._config.claude_timeout_seconds}s",
                        returncode=-1,
                    ),
                )
                return

            returncode = process.returncode or 0

            if returncode != 0 and not state.full_text:
                stderr_text = stderr_bytes.decode("utf-8", errors="replace").strip()
                await self._send(
                    build_claude_stream_error_message(
                        task_id=task_id,
                        host_id=self._host_id,
                        error=f"claude -p exited with code {returncode}: {stderr_text}",
                        returncode=returncode,
                    ),
                )
                return

            # Send completion progress
            state.phase = "completed"
            await self._send_progress(state, task_id)

            # Send stream end
            await self._send(
                build_claude_stream_end_message(
                    task_id=task_id,
                    host_id=self._host_id,
                    session_id=state.session_id,
                    full_text=state.full_text,
                    model_used=state.model or content.model,
                    tokens_input=state.input_tokens,
                    tokens_output=state.output_tokens,
                ),
            )

            await logger.ainfo(
                "claude_runner_completed",
                task_id=task_id,
                session_id=state.session_id,
                model=state.model or content.model,
                text_length=len(state.full_text),
            )

        except Exception as exc:
            await logger.aexception("claude_runner_unexpected_error", task_id=task_id)
            await self._send(
                build_claude_stream_error_message(
                    task_id=task_id,
                    host_id=self._host_id,
                    error=f"Unexpected error: {exc}",
                    returncode=-1,
                ),
            )
        finally:
            self._active_processes.pop(task_id, None)
            self._pending_answers.pop(task_id, None)

    def submit_answer(self, task_id: str, answer: str) -> bool:
        """Feed a user answer for a pending question.

        Returns:
            True if answer was delivered, False if no pending question.
        """
        future = self._pending_answers.get(task_id)
        if future is not None and not future.done():
            future.set_result(answer)
            return True
        return False

    async def cancel(self, task_id: str) -> None:
        """Kill a running claude -p process."""
        proc = self._active_processes.get(task_id)
        if proc is not None and proc.returncode is None:
            proc.kill()
            await logger.ainfo("claude_runner_cancelled", task_id=task_id)

    async def cancel_all(self) -> None:
        """Kill all running claude -p processes (graceful shutdown).

        Once terminate gonderir, 5sn bekler, hala calisiyorsa kill gonderir.
        """
        if not self._active_processes:
            return

        task_ids = list(self._active_processes.keys())
        await logger.ainfo(
            "claude_runner_cancel_all",
            active_count=len(task_ids),
            task_ids=task_ids,
        )

        for _task_id, proc in list(self._active_processes.items()):
            if proc.returncode is not None:
                continue
            try:
                proc.terminate()
            except ProcessLookupError:
                continue

        # Terminate sonrasi kisa bekleme
        await asyncio.sleep(2)

        # Hala calisanlari kill et
        for tid, proc in list(self._active_processes.items()):
            if proc.returncode is not None:
                continue
            try:
                proc.kill()
                await logger.ainfo("claude_runner_force_killed", task_id=tid)
            except ProcessLookupError:
                pass

        # Pending answer future'larini iptal et
        for _task_id, future in list(self._pending_answers.items()):
            if not future.done():
                future.cancel()

        self._active_processes.clear()
        self._pending_answers.clear()

    def _build_command(self, content: ClaudeTaskExecuteContent) -> list[str]:
        """Build the claude CLI command."""
        cmd: list[str] = [
            self._config.claude_binary,
            "-p",
            content.prompt,
            "--output-format",
            "stream-json",
            "--model",
            content.model,
            "--max-turns",
            str(content.max_turns),
            "--verbose",
            "--dangerously-skip-permissions",
        ]

        if content.session_id:
            cmd.extend(["--resume", content.session_id])

        if content.append_system_prompt:
            cmd.extend(["--append-system-prompt", content.append_system_prompt])

        return cmd

    async def _parse_stream(
        self,
        *,
        stdout: asyncio.StreamReader,
        state: _StreamState,
        task_id: str,
    ) -> None:
        """Parse NDJSON stream-json output line by line."""
        async for raw_line in stdout:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line:
                continue

            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                await logger.adebug("claude_runner_unparseable_line", line=line[:200])
                continue

            await self._handle_event(event=event, state=state, task_id=task_id)

    async def _handle_event(
        self,
        *,
        event: dict[str, object],
        state: _StreamState,
        task_id: str,
    ) -> None:
        """Handle a single parsed JSON event from stream-json."""
        event_type = event.get("type")

        # --- Result event ---
        if event_type == "result":
            result_text = event.get("result")
            if isinstance(result_text, str) and result_text:
                if not state.full_text:
                    state.phase = "generating"
                    await self._send(
                        build_claude_stream_delta_message(
                            task_id=task_id,
                            host_id=self._host_id,
                            delta=result_text,
                            index=state.delta_index,
                        ),
                    )
                    state.delta_index += 1
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

        # message_start
        if inner_type == "message_start":
            message = inner.get("message")
            if isinstance(message, dict):
                model = message.get("model")
                if isinstance(model, str):
                    state.model = model
                usage = message.get("usage")
                if isinstance(usage, dict):
                    state.input_tokens = int(usage.get("input_tokens", 0))
            state.phase = "thinking"
            state.stream_started_at = time.monotonic()
            await self._send_progress(state, task_id)

        # content_block_start
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
                                ),
                            )
                            await self._send_progress(state, task_id)

        # content_block_delta
        elif inner_type == "content_block_delta":
            delta = inner.get("delta")
            if not isinstance(delta, dict):
                return

            delta_type = delta.get("type")

            if delta_type == "text_delta":
                text = delta.get("text", "")
                if isinstance(text, str) and text:
                    if state.phase == "tool_calling" and not state.is_collecting_tool_input:
                        state.phase = "generating"
                        await self._send_progress(state, task_id)
                    state.full_text += text
                    await self._send(
                        build_claude_stream_delta_message(
                            task_id=task_id,
                            host_id=self._host_id,
                            delta=text,
                            index=state.delta_index,
                        ),
                    )
                    state.delta_index += 1

            elif delta_type == "input_json_delta":
                partial = delta.get("partial_json", "")
                if isinstance(partial, str) and state.is_collecting_tool_input:
                    state.current_tool_input_json += partial

        # message_delta
        elif inner_type == "message_delta":
            usage = inner.get("usage")
            if isinstance(usage, dict):
                state.output_tokens = int(usage.get("output_tokens", 0))

        # content_block_stop
        elif inner_type == "content_block_stop":
            if state.is_collecting_tool_input:
                state.is_collecting_tool_input = False

                if state.current_tool_name == "AskUserQuestion":
                    await self._handle_ask_user_question(state=state, task_id=task_id)
                else:
                    for tex in reversed(state.tool_executions):
                        if tex.status == "active" and tex.tool_name == state.current_tool_name:
                            tex.completed_at = time.monotonic()
                            tex.status = "completed"
                            tex.input_summary = _tool_input_summary(
                                state.current_tool_name,
                                state.current_tool_input_json,
                            )
                            break
                    await self._send_progress(state, task_id)

                state.current_tool_name = ""
                state.current_tool_input_json = ""

    async def _handle_ask_user_question(
        self,
        *,
        state: _StreamState,
        task_id: str,
    ) -> None:
        """Handle AskUserQuestion tool call from claude -p.

        Sends question to backend, waits for user answer.
        """
        try:
            question_input: dict[str, Any] = json.loads(state.current_tool_input_json)
        except json.JSONDecodeError:
            await logger.awarning(
                "claude_runner_invalid_question_json",
                raw=state.current_tool_input_json[:500],
            )
            return

        await logger.ainfo(
            "claude_runner_question_detected",
            question=str(question_input.get("question", ""))[:100],
        )

        # Send question to backend
        await self._send(
            build_claude_stream_question_message(
                task_id=task_id,
                host_id=self._host_id,
                question_payload=question_input,
            ),
        )

        # Wait for answer from backend (via submit_answer)
        loop = asyncio.get_running_loop()
        future: asyncio.Future[str] = loop.create_future()
        self._pending_answers[task_id] = future

        try:
            await asyncio.wait_for(future, timeout=300.0)
        except TimeoutError:
            await logger.awarning("claude_runner_question_timeout", task_id=task_id)
        finally:
            self._pending_answers.pop(task_id, None)

    async def _send_progress(self, state: _StreamState, task_id: str) -> None:
        """Build and send a progress event."""
        now = time.monotonic()
        steps: list[dict[str, Any]] = []

        # Thinking step
        thinking_done = len(state.tool_executions) > 0 or state.phase in (
            "tool_calling",
            "generating",
            "completed",
        )
        steps.append(
            {
                "id": "phase-thinking",
                "step_type": "thinking",
                "label": "Düşünüyor...",
                "status": "completed" if thinking_done else "active",
            }
        )

        # Tool steps
        for i, tex in enumerate(state.tool_executions):
            duration = (tex.completed_at or now) - tex.started_at
            step: dict[str, Any] = {
                "id": f"tool-{i}",
                "step_type": "tool_calling",
                "label": _tool_display_name(tex.tool_name),
                "status": tex.status,
                "tool_name": tex.tool_name,
            }
            if tex.completed_at:
                step["duration_seconds"] = round(duration, 1)
            if tex.input_summary:
                step["detail"] = tex.input_summary
            steps.append(step)

        # Generating step
        if state.phase in ("generating", "completed"):
            steps.append(
                {
                    "id": "phase-generating",
                    "step_type": "generating",
                    "label": "Cevap hazırlanıyor...",
                    "status": "completed" if state.phase == "completed" else "active",
                }
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
            "starting": "Başlatılıyor...",
            "thinking": "Düşünüyor...",
            "tool_calling": (
                _tool_display_name(state.current_tool_name)
                if state.current_tool_name
                else "İşlem yapılıyor..."
            ),
            "generating": "Cevap hazırlanıyor...",
            "completed": "Tamamlandı",
        }

        await self._send(
            build_claude_stream_progress_message(
                task_id=task_id,
                host_id=self._host_id,
                phase=state.phase,
                phase_label=phase_labels.get(state.phase, state.phase),
                current_tool=state.current_tool_name or None,
                percentage=pct,
                steps=steps,
            ),
        )
