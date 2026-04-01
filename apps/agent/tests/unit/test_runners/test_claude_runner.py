"""Unit tests for ClaudeRunner."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.core.protocol import ClaudeTaskExecuteContent
from agent.runners.claude_runner import ClaudeRunner


def _make_config() -> MagicMock:
    """Create a mock AgentConfig."""
    config = MagicMock()
    config.claude_binary = "claude"
    config.claude_timeout_seconds = 60
    config.project_scan_paths = ["/tmp"]
    return config


def _make_runner(
    sent_messages: list[dict] | None = None,
) -> ClaudeRunner:
    """Create a ClaudeRunner with a mock send callback."""
    messages = sent_messages if sent_messages is not None else []

    async def _send(msg: str) -> None:
        messages.append(json.loads(msg))

    config = _make_config()
    return ClaudeRunner(send_callback=_send, host_id="mac-test", config=config)


def _make_content(**kwargs: object) -> ClaudeTaskExecuteContent:
    """Create a ClaudeTaskExecuteContent with defaults."""
    defaults = {
        "task_id": "task-001",
        "prompt": "Hello",
        "project_dir": "/tmp/project",
        "session_id": None,
        "model": "sonnet",
        "max_turns": 10,
        "append_system_prompt": None,
    }
    defaults.update(kwargs)
    return ClaudeTaskExecuteContent(**defaults)


def _ndjson_lines(*events: dict) -> bytes:
    """Build NDJSON bytes from event dicts."""
    return b"\n".join(json.dumps(e).encode() for e in events) + b"\n"


@pytest.mark.asyncio()
async def test_run_sends_stream_messages() -> None:
    """Verify NDJSON parsing sends delta and end messages."""
    sent: list[dict] = []
    runner = _make_runner(sent)
    content = _make_content()

    # Build fake NDJSON output
    ndjson_events = [
        {
            "type": "stream_event",
            "event": {
                "type": "message_start",
                "message": {"model": "claude-sonnet-4-6", "usage": {"input_tokens": 42}},
            },
        },
        {
            "type": "stream_event",
            "event": {
                "type": "content_block_delta",
                "delta": {"type": "text_delta", "text": "Hello "},
            },
        },
        {
            "type": "stream_event",
            "event": {
                "type": "content_block_delta",
                "delta": {"type": "text_delta", "text": "world!"},
            },
        },
        {
            "type": "stream_event",
            "event": {
                "type": "message_delta",
                "usage": {"output_tokens": 15},
            },
        },
        {
            "type": "result",
            "result": "Hello world!",
            "session_id": "sess-abc",
        },
    ]
    stdout_data = _ndjson_lines(*ndjson_events)

    mock_process = AsyncMock()
    mock_process.stdout = asyncio.StreamReader()
    mock_process.stdout.feed_data(stdout_data)
    mock_process.stdout.feed_eof()
    mock_process.stderr = asyncio.StreamReader()
    mock_process.stderr.feed_data(b"")
    mock_process.stderr.feed_eof()
    mock_process.communicate = AsyncMock(return_value=(b"", b""))
    mock_process.returncode = 0

    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        await runner.run(content)

    # Verify messages sent
    msg_types = [m["type"] for m in sent]
    assert "claude_stream_delta" in msg_types
    assert "claude_stream_end" in msg_types

    # Check delta messages
    deltas = [m for m in sent if m["type"] == "claude_stream_delta"]
    assert len(deltas) >= 2
    assert deltas[0]["content"]["delta"] == "Hello "
    assert deltas[1]["content"]["delta"] == "world!"

    # Check end message
    end_msgs = [m for m in sent if m["type"] == "claude_stream_end"]
    assert len(end_msgs) == 1
    end = end_msgs[0]["content"]
    assert end["session_id"] == "sess-abc"
    assert end["full_text"] == "Hello world!"
    assert end["tokens_input"] == 42
    assert end["tokens_output"] == 15


@pytest.mark.asyncio()
async def test_run_sends_error_on_failure() -> None:
    """Verify error message is sent when process fails."""
    sent: list[dict] = []
    runner = _make_runner(sent)
    content = _make_content()

    mock_process = AsyncMock()
    mock_process.stdout = asyncio.StreamReader()
    mock_process.stdout.feed_data(b"")
    mock_process.stdout.feed_eof()
    mock_process.stderr = asyncio.StreamReader()
    mock_process.stderr.feed_data(b"")
    mock_process.stderr.feed_eof()
    mock_process.communicate = AsyncMock(return_value=(b"", b"something went wrong"))
    mock_process.returncode = 1

    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        await runner.run(content)

    error_msgs = [m for m in sent if m["type"] == "claude_stream_error"]
    assert len(error_msgs) == 1
    assert "exited with code 1" in error_msgs[0]["content"]["error"]


@pytest.mark.asyncio()
async def test_submit_answer_resolves_future() -> None:
    """Verify submit_answer delivers answer to pending question."""
    runner = _make_runner()

    # Simulate a pending answer future
    loop = asyncio.get_running_loop()
    future: asyncio.Future[str] = loop.create_future()
    runner._pending_answers["task-001"] = future

    result = runner.submit_answer("task-001", "Yes")
    assert result is True
    assert future.done()
    assert future.result() == "Yes"


@pytest.mark.asyncio()
async def test_submit_answer_returns_false_for_unknown() -> None:
    """submit_answer should return False for unknown task_id."""
    runner = _make_runner()
    result = runner.submit_answer("unknown-task", "No")
    assert result is False


@pytest.mark.asyncio()
async def test_cancel_kills_process() -> None:
    """cancel() should kill the running process."""
    runner = _make_runner()

    mock_process = MagicMock()
    mock_process.returncode = None
    mock_process.kill = MagicMock()

    runner._active_processes["task-001"] = mock_process

    await runner.cancel("task-001")
    mock_process.kill.assert_called_once()


@pytest.mark.asyncio()
async def test_build_command_includes_flags() -> None:
    """Verify command includes all expected flags."""
    runner = _make_runner()
    content = _make_content(
        session_id="prev-session",
        append_system_prompt="extra context",
        model="opus",
        max_turns=5,
    )

    cmd = runner._build_command(content)
    assert cmd[0] == "claude"
    assert "-p" in cmd
    assert "--output-format" in cmd
    assert "stream-json" in cmd
    assert "--model" in cmd
    assert "opus" in cmd
    assert "--max-turns" in cmd
    assert "5" in cmd
    assert "--dangerously-skip-permissions" in cmd
    assert "--resume" in cmd
    assert "prev-session" in cmd
    assert "--append-system-prompt" in cmd
    assert "extra context" in cmd


@pytest.mark.asyncio()
async def test_run_sends_progress_on_tool_use() -> None:
    """Verify progress messages are sent during tool use."""
    sent: list[dict] = []
    runner = _make_runner(sent)
    content = _make_content()

    ndjson_events = [
        {
            "type": "stream_event",
            "event": {
                "type": "message_start",
                "message": {"model": "claude-sonnet-4-6", "usage": {"input_tokens": 10}},
            },
        },
        {
            "type": "stream_event",
            "event": {
                "type": "content_block_start",
                "content_block": {"type": "tool_use", "name": "Read"},
            },
        },
        {
            "type": "stream_event",
            "event": {
                "type": "content_block_delta",
                "delta": {"type": "input_json_delta", "partial_json": '{"file_path":"/tmp/x"}'},
            },
        },
        {
            "type": "stream_event",
            "event": {"type": "content_block_stop"},
        },
        {
            "type": "result",
            "result": "Done",
            "session_id": "sess-1",
        },
    ]
    stdout_data = _ndjson_lines(*ndjson_events)

    mock_process = AsyncMock()
    mock_process.stdout = asyncio.StreamReader()
    mock_process.stdout.feed_data(stdout_data)
    mock_process.stdout.feed_eof()
    mock_process.stderr = asyncio.StreamReader()
    mock_process.stderr.feed_data(b"")
    mock_process.stderr.feed_eof()
    mock_process.communicate = AsyncMock(return_value=(b"", b""))
    mock_process.returncode = 0

    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        await runner.run(content)

    progress_msgs = [m for m in sent if m["type"] == "claude_stream_progress"]
    assert len(progress_msgs) >= 1
    # Should have tool_calling phase
    phases = [m["content"]["phase"] for m in progress_msgs]
    assert "tool_calling" in phases or "thinking" in phases
