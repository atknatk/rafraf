"""Unit tests for MemoryTool."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

from app.schemas.memory import PersonalMemoryItem
from app.tools.memory_tool import MemoryTool


class TestGetDefinition:
    """Tests for MemoryTool.get_definition."""

    def test_definition_name(self) -> None:
        """get_definition should return tool named memory_manager."""
        tool = MemoryTool()
        definition = tool.get_definition()
        assert definition.name == "memory_manager"

    def test_definition_has_input_schema(self) -> None:
        """get_definition should have a valid input schema."""
        tool = MemoryTool()
        definition = tool.get_definition()
        assert "properties" in definition.input_schema
        assert "action" in definition.input_schema["properties"]  # type: ignore[operator]

    def test_definition_required_fields(self) -> None:
        """get_definition should require action."""
        tool = MemoryTool()
        definition = tool.get_definition()
        assert "required" in definition.input_schema
        assert "action" in definition.input_schema["required"]  # type: ignore[operator]

    def test_definition_has_all_actions(self) -> None:
        """get_definition schema should list all 7 actions."""
        tool = MemoryTool()
        definition = tool.get_definition()
        props = definition.input_schema["properties"]
        actions = props["action"]["enum"]  # type: ignore[index]
        expected = [
            "search_personal",
            "save_facts",
            "get_project_summary",
            "update_project_memory",
            "get_context",
            "get_all_personal",
            "delete_personal",
        ]
        assert actions == expected

    def test_no_approval_required(self) -> None:
        """memory_manager should not require approval."""
        tool = MemoryTool()
        definition = tool.get_definition()
        assert definition.requires_approval is False


class TestExecuteSearchPersonal:
    """Tests for search_personal action."""

    async def test_search_personal_success(self) -> None:
        """search_personal should return matching memories."""
        tool = MemoryTool()
        items = [
            PersonalMemoryItem(id="m1", memory="Short answers", score=0.9),
        ]

        with patch(
            "app.tools.memory_tool.memory_service.search_memories",
            new_callable=AsyncMock,
            return_value=items,
        ):
            result = await tool.execute({
                "action": "search_personal",
                "user_id": "user1",
                "query": "preferences",
                "limit": 5,
            })

        data = json.loads(result)
        assert data["total"] == 1
        assert data["memories"][0]["memory"] == "Short answers"

    async def test_search_personal_missing_params(self) -> None:
        """search_personal should return error for missing params."""
        tool = MemoryTool()
        result = await tool.execute({
            "action": "search_personal",
            "user_id": "",
            "query": "",
        })
        data = json.loads(result)
        assert "error" in data


class TestExecuteSaveFacts:
    """Tests for save_facts action."""

    async def test_save_facts_success(self) -> None:
        """save_facts should call memory_service and return IDs."""
        tool = MemoryTool()

        with patch(
            "app.tools.memory_tool.memory_service.save_conversation_facts",
            new_callable=AsyncMock,
            return_value=["fact_1", "fact_2"],
        ):
            result = await tool.execute({
                "action": "save_facts",
                "user_id": "user1",
                "session_id": "sess_1",
                "messages": [
                    {"role": "user", "content": "Hello"},
                    {"role": "assistant", "content": "Hi"},
                ],
            })

        data = json.loads(result)
        assert data["count"] == 2
        assert "fact_1" in data["saved_memory_ids"]

    async def test_save_facts_missing_params(self) -> None:
        """save_facts should return error for missing params."""
        tool = MemoryTool()
        result = await tool.execute({
            "action": "save_facts",
        })
        data = json.loads(result)
        assert "error" in data


class TestExecuteGetProjectSummary:
    """Tests for get_project_summary action."""

    async def test_get_project_summary_success(self) -> None:
        """get_project_summary should return summary dict."""
        tool = MemoryTool()

        mock_repo = MagicMock()
        mock_summary = {"tech_stack": {"frontend": "React"}}

        with (
            patch("app.tools.memory_tool.async_session_factory") as mock_factory,
            patch(
                "app.tools.memory_tool.memory_service.get_project_summary",
                new_callable=AsyncMock,
                return_value=mock_summary,
            ),
        ):
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_session.commit = AsyncMock()
            mock_factory.return_value = mock_session

            result = await tool.execute({
                "action": "get_project_summary",
                "project_id": "12345678-1234-1234-1234-123456789abc",
            })

        data = json.loads(result)
        assert "summary" in data

    async def test_get_project_summary_invalid_uuid(self) -> None:
        """get_project_summary should return error for invalid UUID."""
        tool = MemoryTool()
        result = await tool.execute({
            "action": "get_project_summary",
            "project_id": "not-a-uuid",
        })
        data = json.loads(result)
        assert "error" in data


class TestExecuteUpdateProjectMemory:
    """Tests for update_project_memory action."""

    async def test_update_success(self) -> None:
        """update_project_memory should update and return status."""
        tool = MemoryTool()

        with (
            patch("app.tools.memory_tool.async_session_factory") as mock_factory,
            patch(
                "app.tools.memory_tool.memory_service.update_project_memory",
                new_callable=AsyncMock,
            ),
        ):
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_session.commit = AsyncMock()
            mock_factory.return_value = mock_session

            result = await tool.execute({
                "action": "update_project_memory",
                "project_id": "12345678-1234-1234-1234-123456789abc",
                "category": "tech_stack",
                "key": "frontend",
                "value": {"framework": "Vue.js"},
                "source": "user_stated",
            })

        data = json.loads(result)
        assert data["status"] == "updated"

    async def test_update_missing_params(self) -> None:
        """update_project_memory should return error for missing params."""
        tool = MemoryTool()
        result = await tool.execute({
            "action": "update_project_memory",
            "project_id": "12345678-1234-1234-1234-123456789abc",
        })
        data = json.loads(result)
        assert "error" in data


class TestExecuteGetAllPersonal:
    """Tests for get_all_personal action."""

    async def test_get_all_success(self) -> None:
        """get_all_personal should return all memories for a user."""
        tool = MemoryTool()
        items = [
            PersonalMemoryItem(id="m1", memory="Fact 1"),
            PersonalMemoryItem(id="m2", memory="Fact 2"),
        ]

        with patch(
            "app.tools.memory_tool.memory_service.get_all_personal_memories",
            new_callable=AsyncMock,
            return_value=items,
        ):
            result = await tool.execute({
                "action": "get_all_personal",
                "user_id": "user1",
            })

        data = json.loads(result)
        assert data["total"] == 2


class TestExecuteDeletePersonal:
    """Tests for delete_personal action."""

    async def test_delete_success(self) -> None:
        """delete_personal should call service and return status."""
        tool = MemoryTool()

        with patch(
            "app.tools.memory_tool.memory_service.delete_personal_memory",
            new_callable=AsyncMock,
            return_value=True,
        ):
            result = await tool.execute({
                "action": "delete_personal",
                "memory_id": "mem_123",
            })

        data = json.loads(result)
        assert data["status"] == "deleted"

    async def test_delete_missing_id(self) -> None:
        """delete_personal should return error for missing memory_id."""
        tool = MemoryTool()
        result = await tool.execute({
            "action": "delete_personal",
        })
        data = json.loads(result)
        assert "error" in data


class TestExecuteUnknownAction:
    """Tests for unknown actions."""

    async def test_unknown_action(self) -> None:
        """execute should return error for unknown action."""
        tool = MemoryTool()
        result = await tool.execute({"action": "nonexistent"})
        data = json.loads(result)
        assert "error" in data
        assert "Bilinmeyen action" in data["error"]

    async def test_missing_action(self) -> None:
        """execute should return error for missing action."""
        tool = MemoryTool()
        result = await tool.execute({})
        data = json.loads(result)
        assert "error" in data
