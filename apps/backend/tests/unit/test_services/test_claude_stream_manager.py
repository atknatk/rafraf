"""Unit tests for ClaudeStreamManager."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.orchestrator.claude_code_runner import ClaudeCodeError
from app.schemas.agent import AgentCapability, AgentRegisterPayload
from app.schemas.messages import MessageDirection, MessageType
from app.services.bridge_registry_service import BridgeRegistryService
from app.services.claude_stream_manager import (
    ClaudeStreamCallbacks,
    ClaudeStreamManager,
    ClaudeStreamResult,
)


def _make_registry_with_agent(host_id: str = "mac-1") -> BridgeRegistryService:
    """Create a registry with one online agent registered.

    Tolerant of two pytest-asyncio loop states:
      * an active loop (auto-mode mid-test) — we run the coroutine to
        completion via ``run_until_complete`` against the already-current
        loop;
      * no active loop (pre-fixture / cross-collection ordering) — we
        spin up a fresh loop, drain the coroutine, and dispose of it so
        we don't leave a dangling default loop.
    """
    registry = BridgeRegistryService()
    payload = AgentRegisterPayload(
        host_id=host_id,
        capabilities=[AgentCapability.CLAUDE_CODE, AgentCapability.SHELL],
        os_info="macOS 15.0",
        version="1.0.0",
    )
    coro = registry.register_agent(payload, f"conn-{host_id}")
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("loop closed")
    except (RuntimeError, DeprecationWarning):
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(coro)
        finally:
            loop.close()
        return registry
    if loop.is_running():
        # Inside an already-running loop (shouldn't happen for fixture
        # setup, but fall back to a fresh loop just in case).
        new_loop = asyncio.new_event_loop()
        try:
            new_loop.run_until_complete(coro)
        finally:
            new_loop.close()
    else:
        loop.run_until_complete(coro)
    return registry


@pytest.fixture
def agent_manager() -> MagicMock:
    """Mock ConnectionManager for agent WebSocket connections."""
    mgr = MagicMock()
    mgr.send_json = AsyncMock(return_value=True)
    return mgr


@pytest.fixture
def csm(agent_manager: MagicMock) -> ClaudeStreamManager:
    registry = _make_registry_with_agent("mac-1")
    return ClaudeStreamManager(agent_registry=registry, agent_manager=agent_manager)


@pytest.mark.asyncio
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


@pytest.mark.asyncio
async def test_dispatch_offline_agent_raises(agent_manager: MagicMock) -> None:
    """Dispatch to offline agent should raise ClaudeCodeError."""
    registry = BridgeRegistryService()
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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

    await csm.handle_stream_end(
        task_id,
        {
            "session_id": "sess-123",
            "full_text": "Hello world!",
            "model_used": "claude-sonnet-4-6",
            "tokens_input": 100,
            "tokens_output": 50,
        },
    )

    assert future.done()
    result = future.result()
    assert isinstance(result, ClaudeStreamResult)
    assert result.session_id == "sess-123"
    assert result.full_text == "Hello world!"
    assert result.model_used == "claude-sonnet-4-6"
    assert result.tokens_input == 100
    assert result.tokens_output == 50


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


# ---------------------------------------------------------------------------
# T1.2 — Agent Teams forwarders.
#
# Each forwarder builds a typed Pydantic payload, wraps it in a server →
# client envelope dict, and pushes via ``ios_manager.send_to_user``. Tests
# below assert:
#   * the message ``type`` matches the expected MessageType,
#   * the ``content`` (post-Pydantic-roundtrip) carries every required
#     field with the right value,
#   * the envelope ``metadata.direction`` is server_to_client,
#   * multi-session multicast via ``send_to_user`` returns the count.
# ---------------------------------------------------------------------------


@pytest.fixture
def ios_manager() -> MagicMock:
    """Mock ConnectionManager for iOS connections — returns 1 from send_to_user."""
    mgr = MagicMock()
    mgr.send_to_user = AsyncMock(return_value=1)
    mgr.get_active_user_ids = MagicMock(return_value=set())
    return mgr


@pytest.fixture
def csm_with_ios(
    agent_manager: MagicMock,
    ios_manager: MagicMock,
) -> ClaudeStreamManager:
    registry = _make_registry_with_agent("mac-1")
    return ClaudeStreamManager(
        agent_registry=registry,
        agent_manager=agent_manager,
        ios_manager=ios_manager,
    )


def _last_envelope(ios_manager: MagicMock) -> dict[str, object]:
    """Pull the last envelope passed to ios_manager.send_to_user."""
    assert ios_manager.send_to_user.await_count >= 1
    args = ios_manager.send_to_user.await_args
    user_id, envelope = args[0]
    assert isinstance(user_id, str)
    assert isinstance(envelope, dict)
    return envelope


@pytest.mark.asyncio
async def test_forward_session_init_pushes_typed_envelope(
    csm_with_ios: ClaudeStreamManager,
    ios_manager: MagicMock,
) -> None:
    """forward_session_init builds SessionInitPayload + pushes to user."""
    sent = await csm_with_ios.forward_session_init(
        user_id="user-1",
        session_id="abc-123",
        model="claude-opus-4",
        permission_mode="acceptEdits",
        api_key_source="claude-code",
        cwd="/workspace",
        agent_teams_enabled=True,
    )
    assert sent == 1
    env = _last_envelope(ios_manager)
    assert env["type"] == MessageType.SESSION_INIT.value
    metadata = env["metadata"]
    assert isinstance(metadata, dict)
    assert metadata["direction"] == MessageDirection.SERVER_TO_CLIENT.value
    assert metadata["session_id"] == "abc-123"
    content = env["content"]
    assert isinstance(content, dict)
    assert content["session_id"] == "abc-123"
    assert content["model"] == "claude-opus-4"
    assert content["permission_mode"] == "acceptEdits"
    assert content["api_key_source"] == "claude-code"
    assert content["cwd"] == "/workspace"
    assert content["agent_teams_enabled"] is True
    # Server-side timestamp must be present + ISO-format-parseable.
    assert isinstance(content["initialized_at"], str)
    datetime.fromisoformat(content["initialized_at"])


@pytest.mark.asyncio
async def test_forward_session_init_uses_provided_timestamp(
    csm_with_ios: ClaudeStreamManager,
    ios_manager: MagicMock,
) -> None:
    """An explicit initialized_at must NOT be overwritten."""
    explicit = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
    await csm_with_ios.forward_session_init(
        user_id="user-1",
        session_id="abc-123",
        model="claude-opus-4",
        permission_mode="acceptEdits",
        api_key_source="claude-code",
        cwd="/workspace",
        agent_teams_enabled=True,
        initialized_at=explicit,
    )
    content = _last_envelope(ios_manager)["content"]
    assert isinstance(content, dict)
    # Pydantic v2 model_dump(mode='json') normalises tz to ``Z``; parse back
    # to an aware datetime to compare semantically (avoids string-format
    # coupling).
    assert isinstance(content["initialized_at"], str)
    parsed = datetime.fromisoformat(content["initialized_at"].replace("Z", "+00:00"))
    assert parsed == explicit


@pytest.mark.asyncio
async def test_forward_subagent_spawned_full_payload(
    csm_with_ios: ClaudeStreamManager,
    ios_manager: MagicMock,
) -> None:
    """forward_subagent_spawned builds SubagentSpawnedPayload."""
    await csm_with_ios.forward_subagent_spawned(
        user_id="user-2",
        session_id="sess-9",
        task_id="task-1",
        name="Lint fixer",
        description="Runs ruff --fix",
        prompt_preview="Please fix the linter errors",
        subagent_type="general",
        isolation="worktree",
    )
    env = _last_envelope(ios_manager)
    assert env["type"] == MessageType.SUBAGENT_SPAWNED.value
    content = env["content"]
    assert isinstance(content, dict)
    assert content["task_id"] == "task-1"
    assert content["name"] == "Lint fixer"
    assert content["description"] == "Runs ruff --fix"
    assert content["prompt_preview"] == "Please fix the linter errors"
    assert content["subagent_type"] == "general"
    assert content["isolation"] == "worktree"
    assert isinstance(content["started_at"], str)


@pytest.mark.asyncio
async def test_forward_subagent_progress_minimum_fields(
    csm_with_ios: ClaudeStreamManager,
    ios_manager: MagicMock,
) -> None:
    """forward_subagent_progress requires task_id/status/activity."""
    await csm_with_ios.forward_subagent_progress(
        user_id="user-3",
        session_id=None,  # session may be None for some bridge envelopes
        task_id="task-9",
        status="in_progress",
        activity="Editing config.toml",
    )
    env = _last_envelope(ios_manager)
    assert env["type"] == MessageType.SUBAGENT_PROGRESS.value
    metadata = env["metadata"]
    assert isinstance(metadata, dict)
    assert metadata["session_id"] is None
    content = env["content"]
    assert isinstance(content, dict)
    assert content["task_id"] == "task-9"
    assert content["status"] == "in_progress"
    assert content["activity"] == "Editing config.toml"


@pytest.mark.asyncio
async def test_forward_subagent_completed_terminal_metrics(
    csm_with_ios: ClaudeStreamManager,
    ios_manager: MagicMock,
) -> None:
    """forward_subagent_completed propagates summary + token counts."""
    await csm_with_ios.forward_subagent_completed(
        user_id="user-4",
        session_id="sess-5",
        task_id="task-77",
        status="completed",
        summary="Fixed 4 lint errors",
        total_tokens=1234,
        tool_uses=8,
        duration_ms=4500,
    )
    env = _last_envelope(ios_manager)
    assert env["type"] == MessageType.SUBAGENT_COMPLETED.value
    content = env["content"]
    assert isinstance(content, dict)
    assert content["task_id"] == "task-77"
    assert content["status"] == "completed"
    assert content["summary"] == "Fixed 4 lint errors"
    assert content["total_tokens"] == 1234
    assert content["tool_uses"] == 8
    assert content["duration_ms"] == 4500


@pytest.mark.asyncio
async def test_forward_rate_limit_info_allowed(
    csm_with_ios: ClaudeStreamManager,
    ios_manager: MagicMock,
) -> None:
    """forward_rate_limit_info wraps RateLimitInfoPayload with allowed status."""
    await csm_with_ios.forward_rate_limit_info(
        user_id="user-5",
        session_id="sess-3",
        status="allowed",
        rate_limit_type="five_hour",
        resets_at=1735689600,
        overage_status="none",
        is_using_overage=False,
    )
    env = _last_envelope(ios_manager)
    assert env["type"] == MessageType.RATE_LIMIT_INFO.value
    content = env["content"]
    assert isinstance(content, dict)
    assert content["status"] == "allowed"
    assert content["rate_limit_type"] == "five_hour"
    assert content["resets_at"] == 1735689600
    assert content["overage_status"] == "none"
    assert content["is_using_overage"] is False


@pytest.mark.asyncio
async def test_forward_rate_limit_info_limited(
    csm_with_ios: ClaudeStreamManager,
    ios_manager: MagicMock,
) -> None:
    """RateLimitInfoPayload accepts the 'limited' status per T1.5 reviewer M2."""
    await csm_with_ios.forward_rate_limit_info(
        user_id="user-5",
        session_id=None,
        status="limited",
        rate_limit_type="five_hour",
        resets_at=1735689600,
        overage_status="active",
        is_using_overage=True,
    )
    content = _last_envelope(ios_manager)["content"]
    assert isinstance(content, dict)
    assert content["status"] == "limited"
    assert content["is_using_overage"] is True


@pytest.mark.asyncio
async def test_forward_session_title_casts_session_id_to_uuid(
    csm_with_ios: ClaudeStreamManager,
    ios_manager: MagicMock,
) -> None:
    """T1.5 reviewer M1: session_id MUST be UUID for SessionTitlePayload."""
    sid_uuid = uuid4()
    sid_str = str(sid_uuid)
    await csm_with_ios.forward_session_title(
        user_id="user-6",
        session_id=sid_str,  # str input — must be coerced
        ai_title="Refactor websocket handler",
    )
    env = _last_envelope(ios_manager)
    assert env["type"] == MessageType.SESSION_TITLE.value
    content = env["content"]
    assert isinstance(content, dict)
    # UUID survives the model_dump(mode='json') round-trip as str.
    assert content["session_id"] == sid_str
    assert content["ai_title"] == "Refactor websocket handler"
    # Server-side timestamp injection (T1.5 M3) — bridge omits generated_at.
    assert isinstance(content["generated_at"], str)
    datetime.fromisoformat(content["generated_at"])


@pytest.mark.asyncio
async def test_forward_session_title_rejects_invalid_uuid(
    csm_with_ios: ClaudeStreamManager,
) -> None:
    """A non-UUID session_id surfaces a ValueError to the caller."""
    with pytest.raises(ValueError, match="badly formed"):
        await csm_with_ios.forward_session_title(
            user_id="user-6",
            session_id="not-a-uuid",
            ai_title="x",
        )


@pytest.mark.asyncio
async def test_forward_session_pr_opened_full_payload(
    csm_with_ios: ClaudeStreamManager,
    ios_manager: MagicMock,
) -> None:
    """forward_session_pr_opened builds SessionPrOpenedPayload."""
    sid_uuid = uuid4()
    await csm_with_ios.forward_session_pr_opened(
        user_id="user-7",
        session_id=sid_uuid,  # UUID input also accepted
        pr_number=42,
        pr_url="https://github.com/org/repo/pull/42",
        pr_repository="org/repo",
    )
    env = _last_envelope(ios_manager)
    assert env["type"] == MessageType.SESSION_PR_OPENED.value
    content = env["content"]
    assert isinstance(content, dict)
    assert content["session_id"] == str(sid_uuid)
    assert content["pr_number"] == 42
    assert content["pr_url"] == "https://github.com/org/repo/pull/42"
    assert content["pr_repository"] == "org/repo"
    # Server-side opened_at injection (T1.5 M3).
    assert isinstance(content["opened_at"], str)
    datetime.fromisoformat(content["opened_at"])


@pytest.mark.asyncio
async def test_forward_usage_report_sends_full_payload(
    csm_with_ios: ClaudeStreamManager,
    ios_manager: MagicMock,
) -> None:
    """forward_usage_report wraps UsageReportPayload + multicasts to user."""
    sent = await csm_with_ios.forward_usage_report(
        user_id="user-8",
        five_hour_pct=42,
        seven_day_pct=18,
        five_hour_resets_at=1735689600,
        seven_day_resets_at=1736294400,
        reported_at=1735680000,
    )
    assert sent == 1
    env = _last_envelope(ios_manager)
    assert env["type"] == MessageType.USAGE_REPORT.value
    content = env["content"]
    assert isinstance(content, dict)
    assert content["five_hour_pct"] == 42
    assert content["seven_day_pct"] == 18
    assert content["five_hour_resets_at"] == 1735689600
    assert content["seven_day_resets_at"] == 1736294400
    assert content["reported_at"] == 1735680000
    # Usage is user-wide, not session-scoped.
    metadata = env["metadata"]
    assert isinstance(metadata, dict)
    assert metadata["session_id"] is None


@pytest.mark.asyncio
async def test_forward_usage_report_multicast_to_multiple_sessions(
    csm_with_ios: ClaudeStreamManager,
    ios_manager: MagicMock,
) -> None:
    """A user with N iOS sessions must see send_to_user return N."""
    # Simulate the user having 3 active iOS sessions (e.g. 3 devices).
    ios_manager.send_to_user = AsyncMock(return_value=3)
    sent = await csm_with_ios.forward_usage_report(
        user_id="user-9",
        five_hour_pct=10,
        seven_day_pct=5,
        five_hour_resets_at=1735689600,
        seven_day_resets_at=1736294400,
        reported_at=1735680000,
    )
    assert sent == 3
    ios_manager.send_to_user.assert_awaited_once()
    # Caller passes user_id + envelope; assert the user_id is right.
    user_arg = ios_manager.send_to_user.await_args[0][0]
    assert user_arg == "user-9"


@pytest.mark.asyncio
async def test_forwarder_skips_when_no_ios_manager(
    agent_manager: MagicMock,
) -> None:
    """forward_* MUST NOT crash when ios_manager wasn't injected (legacy ctor)."""
    # Build the registry async so we don't reuse the running loop helper.
    registry = BridgeRegistryService()
    payload = AgentRegisterPayload(
        host_id="mac-1",
        capabilities=[AgentCapability.CLAUDE_CODE, AgentCapability.SHELL],
        os_info="macOS 15.0",
        version="1.0.0",
    )
    await registry.register_agent(payload, "conn-mac-1")
    csm_legacy = ClaudeStreamManager(
        agent_registry=registry,
        agent_manager=agent_manager,
        # ios_manager intentionally omitted
    )
    sent = await csm_legacy.forward_usage_report(
        user_id="user-x",
        five_hour_pct=0,
        seven_day_pct=0,
        five_hour_resets_at=0,
        seven_day_resets_at=0,
        reported_at=0,
    )
    assert sent == 0


@pytest.mark.asyncio
async def test_forward_session_init_pydantic_validates_required_fields(
    csm_with_ios: ClaudeStreamManager,
) -> None:
    """A missing-required-field bug surfaces as a Pydantic ValidationError."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        # ``model`` is required; passing an empty string is fine, but
        # passing ``None`` (which Pydantic v2 rejects for ``str``) trips
        # the validator. Use a wrong type to exercise the validator.
        await csm_with_ios.forward_session_init(
            user_id="user-1",
            session_id="abc-123",
            model=None,  # type: ignore[arg-type]
            permission_mode="acceptEdits",
            api_key_source="claude-code",
            cwd="/workspace",
            agent_teams_enabled=True,
        )


@pytest.mark.asyncio
async def test_forward_session_init_uuid_str_round_trip() -> None:
    """SessionTitlePayload.session_id must round-trip cleanly as str."""
    # Direct schema test — guards against a future schema change that drops
    # the UUID type and reintroduces the M1 bug from T1.5 review.
    from app.schemas.messages import SessionTitlePayload

    sid = uuid4()
    payload = SessionTitlePayload(
        session_id=sid,
        ai_title="x",
        generated_at=datetime.now(tz=UTC),
    )
    assert isinstance(payload.session_id, UUID)
    dumped = payload.model_dump(mode="json")
    assert dumped["session_id"] == str(sid)


# ---------------------------------------------------------------------------
# Coverage top-up: legacy handle_stream_* paths.
#
# These exercise the few uncovered lines in the legacy claude_task_execute
# flow so the new code keeps coverage on claude_stream_manager.py above
# 90%. They duplicate intent from the integration suite but stay fast.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_stream_delta_unknown_task_logs_and_returns(
    csm: ClaudeStreamManager,
) -> None:
    """A delta for an unregistered task must NOT raise — just log + skip."""
    # No exception expected; nothing observable beyond a warning log line.
    await csm.handle_stream_delta("nonexistent-task", "x", 0)


@pytest.mark.asyncio
async def test_handle_stream_progress_unknown_task_returns(
    csm: ClaudeStreamManager,
) -> None:
    """Progress for an unregistered task must NOT raise."""
    await csm.handle_stream_progress("nonexistent-task", {"phase": "thinking"})


@pytest.mark.asyncio
async def test_handle_stream_progress_invokes_callback(
    csm: ClaudeStreamManager,
) -> None:
    """Progress with a registered callback must reconstruct ToolProgressEvent."""
    received: list[object] = []

    async def _on_progress(event: object) -> None:
        received.append(event)

    callbacks = ClaudeStreamCallbacks(on_tool_progress=_on_progress)
    task_id = await csm.dispatch(
        host_id="mac-1",
        prompt="x",
        session_id=None,
        project_dir=None,
        append_system_prompt=None,
        model="sonnet",
        max_turns=30,
        callbacks=callbacks,
    )
    await csm.handle_stream_progress(
        task_id,
        {
            "phase": "tool_calling",
            "phase_label": "Bash çalışıyor",
            "current_tool": "Bash",
            "percentage": 30,
            "steps": [
                {
                    "id": "s1",
                    "step_type": "tool_calling",
                    "label": "Komut",
                    "status": "active",
                    "tool_name": "Bash",
                }
            ],
        },
    )
    assert len(received) == 1


@pytest.mark.asyncio
async def test_handle_stream_question_unknown_task_noop(
    csm: ClaudeStreamManager,
) -> None:
    """Question for an unregistered task must NOT raise."""
    await csm.handle_stream_question("nonexistent-task", {"question": "x"})


@pytest.mark.asyncio
async def test_handle_stream_question_no_callback_noop(
    csm: ClaudeStreamManager,
) -> None:
    """A registered task without on_question MUST silently skip."""
    callbacks = ClaudeStreamCallbacks()  # no question handler
    task_id = await csm.dispatch(
        host_id="mac-1",
        prompt="x",
        session_id=None,
        project_dir=None,
        append_system_prompt=None,
        model="sonnet",
        max_turns=30,
        callbacks=callbacks,
    )
    await csm.handle_stream_question(task_id, {"question": "x"})


@pytest.mark.asyncio
async def test_handle_stream_end_unknown_task_noop(
    csm: ClaudeStreamManager,
) -> None:
    """Stream end for an unregistered task must NOT raise."""
    await csm.handle_stream_end("nonexistent-task", {})


@pytest.mark.asyncio
async def test_handle_stream_error_unknown_task_noop(
    csm: ClaudeStreamManager,
) -> None:
    """Stream error for an unregistered task must NOT raise."""
    await csm.handle_stream_error("nonexistent-task", "boom")


@pytest.mark.asyncio
async def test_handle_stream_end_callback_exception_swallowed(
    csm: ClaudeStreamManager,
) -> None:
    """If on_stream_end raises, the future MUST still resolve cleanly."""

    async def _bad_end(_text: str) -> None:
        raise RuntimeError("oops")

    callbacks = ClaudeStreamCallbacks(on_stream_end=_bad_end)
    task_id = await csm.dispatch(
        host_id="mac-1",
        prompt="x",
        session_id=None,
        project_dir=None,
        append_system_prompt=None,
        model="sonnet",
        max_turns=30,
        callbacks=callbacks,
    )
    future = csm.get_completion_future(task_id)
    await csm.handle_stream_end(
        task_id,
        {
            "session_id": "s",
            "full_text": "ok",
            "model_used": "m",
            "tokens_input": 0,
            "tokens_output": 0,
        },
    )
    assert future.done()
    assert future.result().full_text == "ok"


@pytest.mark.asyncio
async def test_get_completion_future_unknown_task_raises(
    csm: ClaudeStreamManager,
) -> None:
    """get_completion_future on a missing id MUST raise ValueError."""
    with pytest.raises(ValueError, match="Unknown task_id"):
        csm.get_completion_future("nonexistent")


@pytest.mark.asyncio
async def test_dispatch_send_failure_raises_and_cleans_up(
    agent_manager: MagicMock,
) -> None:
    """A failed send_json MUST raise + remove the half-registered task."""
    agent_manager.send_json = AsyncMock(return_value=False)
    registry = BridgeRegistryService()
    payload = AgentRegisterPayload(
        host_id="mac-1",
        capabilities=[AgentCapability.CLAUDE_CODE, AgentCapability.SHELL],
        os_info="macOS 15.0",
        version="1.0.0",
    )
    await registry.register_agent(payload, "conn-mac-1")
    csm_local = ClaudeStreamManager(
        agent_registry=registry,
        agent_manager=agent_manager,
    )
    with pytest.raises(ClaudeCodeError, match="kopmus"):
        await csm_local.dispatch(
            host_id="mac-1",
            prompt="x",
            session_id=None,
            project_dir=None,
            append_system_prompt=None,
            model="sonnet",
            max_turns=30,
            callbacks=ClaudeStreamCallbacks(),
        )


@pytest.mark.asyncio
async def test_send_question_answer_unknown_task_noop(
    csm: ClaudeStreamManager,
) -> None:
    """send_question_answer on an unknown task is a silent no-op."""
    await csm.send_question_answer("nonexistent-task", "yes")


@pytest.mark.asyncio
async def test_send_question_answer_unknown_connection_noop(
    csm: ClaudeStreamManager,
) -> None:
    """When the agent connection is gone, send is a no-op."""
    callbacks = ClaudeStreamCallbacks()
    task_id = await csm.dispatch(
        host_id="mac-1",
        prompt="x",
        session_id=None,
        project_dir=None,
        append_system_prompt=None,
        model="sonnet",
        max_turns=30,
        callbacks=callbacks,
    )
    # Drop the host so get_connection_id() returns None.
    csm._registry._bridges.clear()  # noqa: SLF001
    await csm.send_question_answer(task_id, "yes")
