"""Unit tests for CostTool."""

import json
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.schemas.cost import BudgetStatusResponse, CostLogEntity
from app.tools.cost_tool import CostTool


class TestGetDefinition:
    """Tests for CostTool.get_definition."""

    def test_definition_name(self) -> None:
        """Should return tool with name 'cost_tracker'."""
        tool = CostTool()
        defn = tool.get_definition()
        assert defn.name == "cost_tracker"

    def test_definition_has_schema(self) -> None:
        """Should return tool with input schema."""
        tool = CostTool()
        defn = tool.get_definition()
        assert "properties" in defn.input_schema
        assert "action" in defn.input_schema["properties"]

    def test_definition_actions(self) -> None:
        """Should define all expected actions."""
        tool = CostTool()
        defn = tool.get_definition()
        actions = defn.input_schema["properties"]["action"]
        assert isinstance(actions, dict)
        expected = {
            "log_usage",
            "get_report",
            "get_budget_status",
            "list_models",
            "get_user_summaries",
        }
        assert set(actions["enum"]) == expected

    def test_definition_no_approval_required(self) -> None:
        """Cost tool should not require approval."""
        tool = CostTool()
        defn = tool.get_definition()
        assert not defn.requires_approval


class TestExecute:
    """Tests for CostTool.execute."""

    async def test_missing_action(self) -> None:
        """Should return error for missing action."""
        tool = CostTool()
        result = await tool.execute({})
        assert "error" in result

    async def test_unknown_action(self) -> None:
        """Should return error for unknown action."""
        tool = CostTool()
        result = await tool.execute({"action": "nonexistent"})
        parsed = json.loads(result)
        assert "error" in parsed

    async def test_list_models_action(self) -> None:
        """Should return model pricing list."""
        tool = CostTool()
        result = await tool.execute({"action": "list_models"})
        parsed = json.loads(result)
        assert isinstance(parsed, list)
        assert len(parsed) >= 3


class TestLogUsage:
    """Tests for CostTool._log_usage."""

    async def test_log_missing_user_id(self) -> None:
        """Should return error when user_id is missing."""
        tool = CostTool()
        result = await tool.execute({
            "action": "log_usage",
            "model": "claude-sonnet-4-5-20250929",
            "input_tokens": 100,
            "output_tokens": 50,
        })
        assert "error" in result

    async def test_log_missing_model(self) -> None:
        """Should return error when model is missing."""
        tool = CostTool()
        result = await tool.execute({
            "action": "log_usage",
            "user_id": str(uuid.uuid4()),
            "input_tokens": 100,
            "output_tokens": 50,
        })
        assert "error" in result

    async def test_log_invalid_user_id(self) -> None:
        """Should return error for invalid UUID."""
        tool = CostTool()
        result = await tool.execute({
            "action": "log_usage",
            "user_id": "not-a-uuid",
            "model": "claude-sonnet-4-5-20250929",
            "input_tokens": 100,
            "output_tokens": 50,
        })
        assert "error" in result

    async def test_log_success(self) -> None:
        """Should record usage and return entity JSON."""
        tool = CostTool()
        user_id = uuid.uuid4()
        now = datetime.now(tz=UTC)

        entity = CostLogEntity(
            id=uuid.uuid4(),
            user_id=user_id,
            model="claude-sonnet-4-5-20250929",
            input_tokens=1000,
            output_tokens=500,
            total_tokens=1500,
            cost_usd=0.0105,
            session_id=None,
            tool_name=None,
            called_at=now,
            created_at=now,
        )

        mock_service = AsyncMock()
        mock_service.record_usage = AsyncMock(return_value=entity)

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with (
            patch.object(tool, "_service", mock_service),
            patch(
                "app.tools.cost_tool.async_session_factory",
                return_value=mock_session,
            ),
        ):
            result = await tool.execute({
                "action": "log_usage",
                "user_id": str(user_id),
                "model": "claude-sonnet-4-5-20250929",
                "input_tokens": 1000,
                "output_tokens": 500,
            })

        parsed = json.loads(result)
        assert parsed["model"] == "claude-sonnet-4-5-20250929"
        assert parsed["total_tokens"] == 1500


class TestGetReport:
    """Tests for CostTool._get_report."""

    async def test_get_report_success(self) -> None:
        """Should return report JSON."""
        tool = CostTool()

        mock_report = MagicMock()
        mock_report.model_dump.return_value = {
            "period": "daily",
            "total_cost_usd": 1.5,
            "total_calls": 10,
        }

        mock_service = AsyncMock()
        mock_service.generate_report = AsyncMock(return_value=mock_report)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with (
            patch.object(tool, "_service", mock_service),
            patch(
                "app.tools.cost_tool.async_session_factory",
                return_value=mock_session,
            ),
        ):
            result = await tool.execute({
                "action": "get_report",
                "period": "daily",
            })

        parsed = json.loads(result)
        assert parsed["period"] == "daily"


class TestGetBudgetStatus:
    """Tests for CostTool._get_budget_status."""

    async def test_budget_status_success(self) -> None:
        """Should return budget status JSON."""
        tool = CostTool()

        mock_status = BudgetStatusResponse(
            daily_cost_usd=5.0,
            monthly_cost_usd=50.0,
            daily_limit_usd=10.0,
            monthly_limit_usd=100.0,
            daily_limit_exceeded=False,
            monthly_limit_exceeded=False,
        )

        mock_service = AsyncMock()
        mock_service.get_budget_status = AsyncMock(return_value=mock_status)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with (
            patch.object(tool, "_service", mock_service),
            patch(
                "app.tools.cost_tool.async_session_factory",
                return_value=mock_session,
            ),
        ):
            result = await tool.execute({
                "action": "get_budget_status",
                "daily_limit_usd": 10.0,
                "monthly_limit_usd": 100.0,
            })

        parsed = json.loads(result)
        assert not parsed["daily_limit_exceeded"]
        assert parsed["daily_cost_usd"] == 5.0
