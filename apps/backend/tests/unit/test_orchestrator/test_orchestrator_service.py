"""Unit tests for the orchestrator service module."""

from unittest.mock import AsyncMock, MagicMock, patch

from app.schemas.orchestrator import OrchestratorResponse
from app.services.orchestrator_service import OrchestratorService, get_tool_registry


class TestGetToolRegistry:
    """Tests for the get_tool_registry function."""

    def test_returns_singleton(self) -> None:
        """get_tool_registry should return the same instance."""
        registry1 = get_tool_registry()
        registry2 = get_tool_registry()
        assert registry1 is registry2

    def test_returns_tool_registry(self) -> None:
        """get_tool_registry should return a ToolRegistry instance."""
        from app.orchestrator.tool_registry import ToolRegistry

        registry = get_tool_registry()
        assert isinstance(registry, ToolRegistry)


class TestOrchestratorService:
    """Tests for the OrchestratorService class."""

    @patch("app.services.orchestrator_service.OrchestratorAgent")
    @patch("app.services.orchestrator_service.get_tool_registry")
    async def test_process_user_message_success(
        self,
        _mock_get_registry: MagicMock,  # noqa: PT019
        mock_agent_cls: MagicMock,
    ) -> None:
        """Successful message processing should return a response."""
        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent
        mock_agent.process_message = AsyncMock(
            return_value=OrchestratorResponse(
                session_id="sess_1",
                response_text="AI says hello",
                model_used="claude-sonnet",
                tokens_input=100,
                tokens_output=50,
                tool_calls_count=0,
            )
        )

        service = OrchestratorService()
        response = await service.process_user_message(
            session_id="sess_1",
            user_id="user_1",
            message="Hello",
        )

        assert response.response_text == "AI says hello"
        assert response.model_used == "claude-sonnet"

    @patch("app.services.orchestrator_service.OrchestratorAgent")
    @patch("app.services.orchestrator_service.get_tool_registry")
    async def test_process_user_message_with_project_id(
        self,
        _mock_get_registry: MagicMock,  # noqa: PT019
        mock_agent_cls: MagicMock,
    ) -> None:
        """Project ID should be passed to the orchestrator."""
        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent
        mock_agent.process_message = AsyncMock(
            return_value=OrchestratorResponse(
                session_id="sess_1",
                response_text="Project info",
                model_used="claude-sonnet",
                tokens_input=100,
                tokens_output=50,
                tool_calls_count=0,
            )
        )

        service = OrchestratorService()
        response = await service.process_user_message(
            session_id="sess_1",
            user_id="user_1",
            message="Project status",
            project_id="project-x",
        )

        assert response.response_text == "Project info"
        call_args = mock_agent.process_message.call_args
        request = call_args[0][0]
        assert request.project_id == "project-x"

    @patch("app.services.orchestrator_service.OrchestratorAgent")
    @patch("app.services.orchestrator_service.get_tool_registry")
    async def test_process_user_message_max_iterations_handled(
        self,
        _mock_get_registry: MagicMock,  # noqa: PT019
        mock_agent_cls: MagicMock,
    ) -> None:
        """MaxIterationsReachedError should be handled gracefully."""
        from app.orchestrator.agent import MaxIterationsReachedError

        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent
        mock_agent.process_message = AsyncMock(side_effect=MaxIterationsReachedError())

        service = OrchestratorService()
        response = await service.process_user_message(
            session_id="sess_1",
            user_id="user_1",
            message="Complex task",
        )

        assert "fazla adim" in response.response_text
        assert response.model_used == "none"

    @patch("app.services.orchestrator_service.OrchestratorAgent")
    @patch("app.services.orchestrator_service.get_tool_registry")
    async def test_process_user_message_api_error_handled(
        self,
        _mock_get_registry: MagicMock,  # noqa: PT019
        mock_agent_cls: MagicMock,
    ) -> None:
        """ClaudeAPIError should be handled gracefully."""
        from app.orchestrator.agent import ClaudeAPIError

        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent
        mock_agent.process_message = AsyncMock(side_effect=ClaudeAPIError("API down"))

        service = OrchestratorService()
        response = await service.process_user_message(
            session_id="sess_1",
            user_id="user_1",
            message="Hello",
        )

        assert "kullanilamiyor" in response.response_text
        assert response.model_used == "none"

    @patch("app.services.orchestrator_service.OrchestratorAgent")
    @patch("app.services.orchestrator_service.get_tool_registry")
    async def test_clear_session(
        self,
        _mock_get_registry: MagicMock,  # noqa: PT019
        mock_agent_cls: MagicMock,
    ) -> None:
        """clear_session should delegate to the agent."""
        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent

        service = OrchestratorService()
        service.clear_session("sess_1")

        mock_agent.clear_conversation.assert_called_once_with("sess_1")

    @patch("app.services.orchestrator_service.OrchestratorAgent")
    @patch("app.services.orchestrator_service.get_tool_registry")
    async def test_progress_callback_forwarded(
        self,
        _mock_get_registry: MagicMock,  # noqa: PT019
        mock_agent_cls: MagicMock,
    ) -> None:
        """Progress callback should be forwarded to the agent."""
        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent
        mock_agent.process_message = AsyncMock(
            return_value=OrchestratorResponse(
                session_id="sess_1",
                response_text="Done",
                model_used="claude-sonnet",
                tokens_input=100,
                tokens_output=50,
                tool_calls_count=1,
            )
        )

        service = OrchestratorService()
        progress_cb = AsyncMock()
        await service.process_user_message(
            session_id="sess_1",
            user_id="user_1",
            message="Run tool",
            progress_callback=progress_cb,
        )

        call_kwargs = mock_agent.process_message.call_args[1]
        assert call_kwargs["progress_callback"] is progress_cb
