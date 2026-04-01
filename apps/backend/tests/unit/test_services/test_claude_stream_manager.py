"""Unit tests for ClaudeStreamManager."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.orchestrator.claude_code_runner import ClaudeCodeError
from app.schemas.agent import AgentCapability, AgentRegisterPayload
from app.services.agent_registry_service import AgentRegistryService
from app.services.claude_stream_manager import (
    ClaudeStreamCallbacks,
    ClaudeStreamManager,
    ClaudeStreamResult,
)


def _make_registry_with_agent(host_id: str = "mac-1") -> AgentRegistryService:
    """Create a registry with one online agent registered."""
    registry = AgentRegistryService()
    loop = asyncio.get_event_loop()
    payload = AgentRegisterPayload(
        host_id=host_id,
        capabilities=[AgentCapability.CLAUDE_CODE, AgentCapability.SHELL],
        os_info="macOS 15.0",
        version="1.0.0",
    )
    loop.run_until_complete(registry.register_agent(payload, f"conn-{host_id}"))
    return registry


@pytest.fixture()
def agent_manager() -> MagicMock:
    """Mock ConnectionManager for agent WebSocket connections."""
    mgr = MagicMock()
    mgr.send_json = AsyncMock(return_value=True)
    return mgr


@pytest.fixture()
def csm(agent_manager: MagicMock) -> ClaudeStreamManager:
    registry = _make_registry_with_agent("mac-1")
    return ClaudeStreamManager(agent_registry=registry, agent_manager=agent_manager)


@pytest.mark.asyncio()
async def test_dispatch_sends_claude_task_execute(
    csm: ClaudeStreamManager,
    agent_manager: MagicMock,
) -> None:
    """Dispatch should send claude_task_execute message to the agent."""
    callbacks = ClaudeStreamCallbacks()
    task_id = await csm.dispatch(
        host_id="mac-1",
        prompt="Hello",
        session_id=None,
        project_dir="/tmp/project",
        append_system_prompt="context",
        model="sonnet",
        max_turns=30,
        callbacks=callbacks,
    )

    assert task_id
    agent_manager.send_json.assert_called_once()
    call_args = agent_manager.send_json.call_args
    conn_id = call_args[0][0]
    message = call_args[0][1]

    assert conn_id == "conn-mac-1"
    assert message["type"] == "claude_task_execute"
    assert message["content"]["task_id"] == task_id
    assert message["content"]["prompt"] == "Hello"
    assert message["content"]["model"] == "sonnet"


@pytest.mark.asyncio()
async def test_dispatch_offline_agent_raises(agent_manager: MagicMock) -> None:
    """Dispatch to offline agent should raise ClaudeCodeError."""
    registry = AgentRegistryService()
    csm = ClaudeStreamManager(agent_registry=registry, agent_manager=agent_manager)

    with pytest.raises(ClaudeCodeError, match="bulunamadi"):
        await csm.dispatch(
            host_id="nonexistent",
            prompt="Hello",
            session_id=None,
            project_dir=None,
            append_system_prompt=None,
            model="sonnet",
            max_turns=30,
            callbacks=ClaudeStreamCallbacks(),
        )


@pytest.mark.asyncio()
async def test_handle_stream_delta_calls_callback(csm: ClaudeStreamManager) -> None:
    """Stream delta should be forwarded to on_text_delta callback."""
    delta_calls: list[tuple[str, int]] = []

    async def _on_delta(text: str, idx: int) -> None:
        delta_calls.append((text, idx))

    callbacks = ClaudeStreamCallbacks(on_text_delta=_on_delta)
    task_id = await csm.dispatch(
        host_id="mac-1",
        prompt="test",
        session_id=None,
        project_dir=None,
        append_system_prompt=None,
        model="sonnet",
        max_turns=30,
        callbacks=callbacks,
    )

    await csm.handle_stream_delta(task_id, "Hello ", 0)
    await csm.handle_stream_delta(task_id, "world!", 1)

    assert delta_calls == [("Hello ", 0), ("world!", 1)]


@pytest.mark.asyncio()
async def test_handle_stream_end_resolves_future(csm: ClaudeStreamManager) -> None:
    """Stream end should resolve the completion future with result data."""
    callbacks = ClaudeStreamCallbacks()
    task_id = await csm.dispatch(
        host_id="mac-1",
        prompt="test",
        session_id=None,
        project_dir=None,
        append_system_prompt=None,
        model="sonnet",
        max_turns=30,
        callbacks=callbacks,
    )

    future = csm.get_completion_future(task_id)
    assert not future.done()

    await csm.handle_stream_end(task_id, {
        "session_id": "sess-123",
        "full_text": "Hello world!",
        "model_used": "claude-sonnet-4-6",
        "tokens_input": 100,
        "tokens_output": 50,
    })

    assert future.done()
    result = future.result()
    assert isinstance(result, ClaudeStreamResult)
    assert result.session_id == "sess-123"
    assert result.full_text == "Hello world!"
    assert result.model_used == "claude-sonnet-4-6"
    assert result.tokens_input == 100
    assert result.tokens_output == 50


@pytest.mark.asyncio()
async def test_handle_stream_error_resolves_future(csm: ClaudeStreamManager) -> None:
    """Stream error should resolve the completion future with exception."""
    callbacks = ClaudeStreamCallbacks()
    task_id = await csm.dispatch(
        host_id="mac-1",
        prompt="test",
        session_id=None,
        project_dir=None,
        append_system_prompt=None,
        model="sonnet",
        max_turns=30,
        callbacks=callbacks,
    )

    future = csm.get_completion_future(task_id)

    await csm.handle_stream_error(task_id, "Process crashed", returncode=1)

    assert future.done()
    with pytest.raises(ClaudeCodeError, match="Process crashed"):
        future.result()


@pytest.mark.asyncio()
async def test_question_answer_roundtrip(
    csm: ClaudeStreamManager,
    agent_manager: MagicMock,
) -> None:
    """Question should forward to callback and answer should go back to agent."""
    question_received: list[dict] = []

    async def _on_question(payload: dict) -> str | None:
        question_received.append(payload)
        return "Yes, proceed"

    callbacks = ClaudeStreamCallbacks(on_question=_on_question)
    task_id = await csm.dispatch(
        host_id="mac-1",
        prompt="test",
        session_id=None,
        project_dir=None,
        append_system_prompt=None,
        model="sonnet",
        max_turns=30,
        callbacks=callbacks,
    )

    # Reset send_json call count after dispatch
    agent_manager.send_json.reset_mock()

    await csm.handle_stream_question(task_id, {"question": "Continue?"})

    # Give the background task time to run
    await asyncio.sleep(0.1)

    assert len(question_received) == 1
    assert question_received[0] == {"question": "Continue?"}

    # Answer should have been sent back to agent
    agent_manager.send_json.assert_called_once()
    answer_msg = agent_manager.send_json.call_args[0][1]
    assert answer_msg["type"] == "claude_question_answer"
    assert answer_msg["content"]["task_id"] == task_id
    assert answer_msg["content"]["answer"] == "Yes, proceed"
