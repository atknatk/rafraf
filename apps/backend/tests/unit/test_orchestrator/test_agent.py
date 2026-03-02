"""Unit tests for the OrchestratorAgent module."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.orchestrator.agent import (
    MAX_ITERATIONS,
    ClaudeAPIError,
    OrchestratorAgent,
    OrchestratorError,
)
from app.orchestrator.tool_registry import ToolDefinition, ToolRegistry
from app.schemas.orchestrator import OrchestratorRequest


def _make_text_response(
    text: str = "AI response",
    input_tokens: int = 100,
    output_tokens: int = 50,
) -> MagicMock:
    """Create a mock Claude API text response."""
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = text

    usage = MagicMock()
    usage.input_tokens = input_tokens
    usage.output_tokens = output_tokens

    response = MagicMock()
    response.content = [text_block]
    response.usage = usage
    return response


def _make_tool_use_response(
    tool_name: str = "test_tool",
    tool_input: dict[str, object] | None = None,
    input_tokens: int = 100,
    output_tokens: int = 50,
) -> MagicMock:
    """Create a mock Claude API tool_use response."""
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.id = "tool_call_123"
    tool_block.name = tool_name
    tool_block.input = tool_input or {"action": "test"}

    usage = MagicMock()
    usage.input_tokens = input_tokens
    usage.output_tokens = output_tokens

    response = MagicMock()
    response.content = [tool_block]
    response.usage = usage
    return response


def _make_registry_with_tool() -> tuple[ToolRegistry, AsyncMock]:
    """Create a ToolRegistry with a mock tool registered."""
    registry = ToolRegistry()
    handler = AsyncMock(return_value="tool_output")
    definition = ToolDefinition(
        name="test_tool",
        description="A test tool",
        input_schema={"type": "object", "properties": {}},
    )
    registry.register(definition, handler)
    return registry, handler


class TestOrchestratorError:
    """Tests for OrchestratorError classes."""

    def test_orchestrator_error_message(self) -> None:
        """OrchestratorError should store the message."""
        error = OrchestratorError("test error")
        assert error.message == "test error"
        assert str(error) == "test error"

    def test_claude_api_error(self) -> None:
        """ClaudeAPIError should be an OrchestratorError."""
        error = ClaudeAPIError("API failed")
        assert isinstance(error, OrchestratorError)
        assert error.message == "API failed"


class TestOrchestratorAgent:
    """Tests for the OrchestratorAgent class."""

    @patch("app.orchestrator.agent.get_settings")
    @patch("app.orchestrator.agent.anthropic.AsyncAnthropic")
    async def test_process_text_message_returns_response(
        self,
        mock_anthropic_cls: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        """Processing a text message should return an OrchestratorResponse."""
        mock_settings.return_value.anthropic_api_key = "test-key"
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create = AsyncMock(
            return_value=_make_text_response("Merhaba!")
        )

        registry = ToolRegistry()
        agent = OrchestratorAgent(registry)
        request = OrchestratorRequest(
            session_id="sess_1",
            user_id="user_1",
            message="Merhaba",
        )

        response = await agent.process_message(request)

        assert response.session_id == "sess_1"
        assert response.response_text == "Merhaba!"
        assert response.tokens_input == 100
        assert response.tokens_output == 50
        assert response.tool_calls_count == 0

    @patch("app.orchestrator.agent.get_settings")
    @patch("app.orchestrator.agent.anthropic.AsyncAnthropic")
    async def test_process_message_with_tool_call(
        self,
        mock_anthropic_cls: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        """Processing should execute tool calls and continue the loop."""
        mock_settings.return_value.anthropic_api_key = "test-key"
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        # First call: tool_use, second call: text response
        mock_client.messages.create = AsyncMock(
            side_effect=[
                _make_tool_use_response("test_tool"),
                _make_text_response("Tool result processed"),
            ]
        )

        registry, handler = _make_registry_with_tool()
        agent = OrchestratorAgent(registry)
        request = OrchestratorRequest(
            session_id="sess_1",
            user_id="user_1",
            message="Run the test tool",
        )

        response = await agent.process_message(request)

        assert response.response_text == "Tool result processed"
        assert response.tool_calls_count == 1
        handler.assert_awaited_once()

    @patch("app.orchestrator.agent.get_settings")
    @patch("app.orchestrator.agent.anthropic.AsyncAnthropic")
    async def test_process_message_unregistered_tool(
        self,
        mock_anthropic_cls: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        """Calling an unregistered tool should return an error result."""
        mock_settings.return_value.anthropic_api_key = "test-key"
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        mock_client.messages.create = AsyncMock(
            side_effect=[
                _make_tool_use_response("nonexistent_tool"),
                _make_text_response("Understood"),
            ]
        )

        registry = ToolRegistry()
        agent = OrchestratorAgent(registry)
        request = OrchestratorRequest(
            session_id="sess_1",
            user_id="user_1",
            message="Do something",
        )

        response = await agent.process_message(request)
        assert response.tool_calls_count == 1
        assert response.response_text == "Understood"

    @patch("app.orchestrator.agent.get_settings")
    @patch("app.orchestrator.agent.anthropic.AsyncAnthropic")
    async def test_progress_callback_called(
        self,
        mock_anthropic_cls: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        """Progress callback should be called during tool execution."""
        mock_settings.return_value.anthropic_api_key = "test-key"
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        mock_client.messages.create = AsyncMock(
            side_effect=[
                _make_tool_use_response("test_tool"),
                _make_text_response("Done"),
            ]
        )

        registry, _ = _make_registry_with_tool()
        agent = OrchestratorAgent(registry)
        progress_cb = AsyncMock()

        request = OrchestratorRequest(
            session_id="sess_1",
            user_id="user_1",
            message="Run tool",
        )

        await agent.process_message(request, progress_callback=progress_cb)
        progress_cb.assert_awaited_once_with("test_tool", 1, MAX_ITERATIONS)

    @patch("app.orchestrator.agent.get_settings")
    @patch("app.orchestrator.agent.anthropic.AsyncAnthropic")
    async def test_tool_execution_error_handled(
        self,
        mock_anthropic_cls: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        """Tool execution errors should be returned as error results."""
        mock_settings.return_value.anthropic_api_key = "test-key"
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        mock_client.messages.create = AsyncMock(
            side_effect=[
                _make_tool_use_response("test_tool"),
                _make_text_response("Error handled"),
            ]
        )

        registry = ToolRegistry()
        failing_handler = AsyncMock(side_effect=RuntimeError("Tool crashed"))
        definition = ToolDefinition(
            name="test_tool",
            description="A test tool",
            input_schema={"type": "object", "properties": {}},
        )
        registry.register(definition, failing_handler)

        agent = OrchestratorAgent(registry)
        request = OrchestratorRequest(
            session_id="sess_1",
            user_id="user_1",
            message="Run failing tool",
        )

        response = await agent.process_message(request)
        assert response.tool_calls_count == 1

    @patch("app.orchestrator.agent.get_settings")
    @patch("app.orchestrator.agent.anthropic.AsyncAnthropic")
    async def test_approval_required_tool_returns_error(
        self,
        mock_anthropic_cls: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        """Tools requiring approval should return an error result."""
        mock_settings.return_value.anthropic_api_key = "test-key"
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        mock_client.messages.create = AsyncMock(
            side_effect=[
                _make_tool_use_response("deploy_tool"),
                _make_text_response("Approval needed"),
            ]
        )

        registry = ToolRegistry()
        definition = ToolDefinition(
            name="deploy_tool",
            description="Deploy to production",
            input_schema={"type": "object", "properties": {}},
            requires_approval=True,
            approval_category="deploy",
        )
        registry.register(definition, AsyncMock())

        agent = OrchestratorAgent(registry)
        request = OrchestratorRequest(
            session_id="sess_1",
            user_id="user_1",
            message="Deploy",
        )

        response = await agent.process_message(request)
        assert response.tool_calls_count == 1

    @patch("app.orchestrator.agent.get_settings")
    @patch("app.orchestrator.agent.anthropic.AsyncAnthropic")
    async def test_clear_conversation(
        self,
        mock_anthropic_cls: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        """Clearing conversation should remove session history."""
        mock_settings.return_value.anthropic_api_key = "test-key"
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create = AsyncMock(
            return_value=_make_text_response()
        )

        registry = ToolRegistry()
        agent = OrchestratorAgent(registry)

        request = OrchestratorRequest(
            session_id="sess_1",
            user_id="user_1",
            message="Hello",
        )
        await agent.process_message(request)

        # Conversation should exist
        assert "sess_1" in agent._conversations

        # Clear it
        agent.clear_conversation("sess_1")
        assert "sess_1" not in agent._conversations

    @patch("app.orchestrator.agent.asyncio.sleep", new_callable=AsyncMock)
    @patch("app.orchestrator.agent.get_settings")
    @patch("app.orchestrator.agent.anthropic.AsyncAnthropic")
    async def test_claude_api_retry_on_rate_limit(
        self,
        mock_anthropic_cls: MagicMock,
        mock_settings: MagicMock,
        _mock_sleep: AsyncMock,
    ) -> None:
        """Rate limit errors should trigger retries."""
        import anthropic as anthropic_mod

        mock_settings.return_value.anthropic_api_key = "test-key"
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        rate_limit_response = MagicMock()
        rate_limit_response.status_code = 429
        rate_limit_response.headers = {}

        mock_client.messages.create = AsyncMock(
            side_effect=[
                anthropic_mod.RateLimitError(
                    message="rate limited",
                    response=rate_limit_response,
                    body=None,
                ),
                _make_text_response("Success after retry"),
            ]
        )

        registry = ToolRegistry()
        agent = OrchestratorAgent(registry)
        request = OrchestratorRequest(
            session_id="sess_1",
            user_id="user_1",
            message="test",
        )

        response = await agent.process_message(request)
        assert response.response_text == "Success after retry"
        assert mock_client.messages.create.await_count == 2

    @patch("app.orchestrator.agent.asyncio.sleep", new_callable=AsyncMock)
    @patch("app.orchestrator.agent.get_settings")
    @patch("app.orchestrator.agent.anthropic.AsyncAnthropic")
    async def test_claude_api_all_retries_exhausted(
        self,
        mock_anthropic_cls: MagicMock,
        mock_settings: MagicMock,
        _mock_sleep: AsyncMock,
    ) -> None:
        """Exhausting all retries should raise ClaudeAPIError."""
        import anthropic as anthropic_mod

        mock_settings.return_value.anthropic_api_key = "test-key"
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        rate_limit_response = MagicMock()
        rate_limit_response.status_code = 429
        rate_limit_response.headers = {}

        mock_client.messages.create = AsyncMock(
            side_effect=anthropic_mod.RateLimitError(
                message="rate limited",
                response=rate_limit_response,
                body=None,
            )
        )

        registry = ToolRegistry()
        agent = OrchestratorAgent(registry)
        request = OrchestratorRequest(
            session_id="sess_1",
            user_id="user_1",
            message="test",
        )

        with pytest.raises(ClaudeAPIError, match="failed after"):
            await agent.process_message(request)
