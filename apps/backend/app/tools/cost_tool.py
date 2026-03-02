"""Cost Tracker Tool - Claude AI tool for cost tracking and reporting.

Cloud tool that runs on EKS (no host agent required).
Provides cost logging, report generation, budget status checks, and model pricing info.
"""

import json
import uuid
from datetime import date, datetime

import structlog

from app.core.database import async_session_factory
from app.orchestrator.tool_registry import ToolDefinition
from app.repositories.cost_repository import CostRepository
from app.services.cost_service import CostService, cost_service
from app.tools.base import BaseTool

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

_COST_TOOL_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": [
                "log_usage",
                "get_report",
                "get_budget_status",
                "list_models",
                "get_user_summaries",
            ],
            "description": "Yapilacak maliyet islemi",
        },
        "user_id": {
            "type": "string",
            "description": "Kullanici UUID (log_usage icin zorunlu, filtreleme icin opsiyonel)",
        },
        "model": {
            "type": "string",
            "description": "AI model adi (log_usage icin zorunlu)",
        },
        "input_tokens": {
            "type": "integer",
            "description": "Input token sayisi (log_usage icin zorunlu)",
        },
        "output_tokens": {
            "type": "integer",
            "description": "Output token sayisi (log_usage icin zorunlu)",
        },
        "session_id": {
            "type": "string",
            "description": "Oturum ID (log_usage icin opsiyonel)",
        },
        "tool_name": {
            "type": "string",
            "description": "Tool adi (log_usage icin opsiyonel)",
        },
        "period": {
            "type": "string",
            "enum": ["daily", "monthly"],
            "description": "Rapor periyodu (get_report icin, varsayilan: daily)",
        },
        "target_date": {
            "type": "string",
            "description": "Rapor tarihi YYYY-MM-DD formatinda (get_report icin opsiyonel)",
        },
        "daily_limit_usd": {
            "type": "number",
            "description": "Gunluk limit USD (get_budget_status icin opsiyonel)",
        },
        "monthly_limit_usd": {
            "type": "number",
            "description": "Aylik limit USD (get_budget_status icin opsiyonel)",
        },
    },
    "required": ["action"],
}


class CostTool(BaseTool):
    """Cost Tracker tool for Claude AI.

    Provides cost tracking and reporting as a Claude tool. Registered with the
    tool registry and called by the AI orchestrator during tool-calling loops.
    """

    def __init__(self) -> None:
        self._service: CostService = cost_service

    def get_definition(self) -> ToolDefinition:
        """Return the tool definition for Claude API.

        Returns:
            ToolDefinition with cost_tracker schema.
        """
        return ToolDefinition(
            name="cost_tracker",
            description=(
                "AI API maliyet takibi. Token kullanimi kaydetme, gunluk/aylik rapor olusturma, "
                "budget durum kontrolu, model fiyatlama listesi. "
                "Maliyet kaydi onay gerektirmez."
            ),
            input_schema=_COST_TOOL_SCHEMA,
            requires_approval=False,
            approval_category=None,
        )

    async def execute(self, params: dict[str, object]) -> str:
        """Execute a cost tracker action.

        Args:
            params: Tool input parameters from Claude.

        Returns:
            JSON string result.
        """
        action = str(params.get("action", ""))

        if not action:
            return '{"error": "action parametresi zorunludur"}'

        await logger.ainfo("cost_tool_execute", action=action)

        try:
            return await self._dispatch(action, params)
        except Exception as exc:
            await logger.aexception("cost_tool_error", action=action)
            return f'{{"error": "Maliyet islemi hatasi: {exc}"}}'

    async def _dispatch(self, action: str, params: dict[str, object]) -> str:
        """Dispatch to the appropriate action handler.

        Args:
            action: Action name.
            params: Full params dict.

        Returns:
            JSON string result.
        """
        if action == "log_usage":
            return await self._log_usage(params)
        if action == "get_report":
            return await self._get_report(params)
        if action == "get_budget_status":
            return await self._get_budget_status(params)
        if action == "list_models":
            return self._list_models()
        if action == "get_user_summaries":
            return await self._get_user_summaries(params)
        return f'{{"error": "Bilinmeyen action: {action}"}}'

    async def _log_usage(self, params: dict[str, object]) -> str:
        user_id_str = str(params.get("user_id", ""))
        model = str(params.get("model", ""))
        input_tokens_raw = params.get("input_tokens", 0)
        output_tokens_raw = params.get("output_tokens", 0)

        if not user_id_str or not model:
            return '{"error": "user_id ve model parametreleri zorunludur"}'

        try:
            user_id = uuid.UUID(user_id_str)
        except ValueError:
            return '{"error": "Gecersiz user_id formati"}'

        input_tokens = int(str(input_tokens_raw)) if input_tokens_raw else 0
        output_tokens = int(str(output_tokens_raw)) if output_tokens_raw else 0
        session_id = str(params["session_id"]) if params.get("session_id") else None
        tool_name = str(params["tool_name"]) if params.get("tool_name") else None

        async with async_session_factory() as session:
            repo = CostRepository(session)
            entity = await self._service.record_usage(
                repo,
                user_id=user_id,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                session_id=session_id,
                tool_name=tool_name,
            )
            await session.commit()

        return json.dumps(entity.model_dump(), default=str, ensure_ascii=False, indent=2)

    async def _get_report(self, params: dict[str, object]) -> str:
        period = str(params.get("period", "daily"))
        target_date_str = str(params.get("target_date", "")) if params.get("target_date") else None
        user_id_str = str(params.get("user_id", "")) if params.get("user_id") else None

        target_date: date | None = None
        if target_date_str:
            target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()

        user_id: uuid.UUID | None = None
        if user_id_str:
            user_id = uuid.UUID(user_id_str)

        async with async_session_factory() as session:
            repo = CostRepository(session)
            report = await self._service.generate_report(
                repo,
                period=period,
                target_date=target_date,
                user_id=user_id,
            )

        return json.dumps(report.model_dump(), default=str, ensure_ascii=False, indent=2)

    async def _get_budget_status(self, params: dict[str, object]) -> str:
        user_id_str = str(params.get("user_id", "")) if params.get("user_id") else None
        daily_limit_raw = params.get("daily_limit_usd")
        monthly_limit_raw = params.get("monthly_limit_usd")

        user_id: uuid.UUID | None = None
        if user_id_str:
            user_id = uuid.UUID(user_id_str)

        daily_limit: float | None = (
            float(str(daily_limit_raw)) if daily_limit_raw is not None else None
        )
        monthly_limit: float | None = (
            float(str(monthly_limit_raw)) if monthly_limit_raw is not None else None
        )

        async with async_session_factory() as session:
            repo = CostRepository(session)
            status_resp = await self._service.get_budget_status(
                repo,
                user_id=user_id,
                daily_limit_usd=daily_limit,
                monthly_limit_usd=monthly_limit,
            )

        return json.dumps(status_resp.model_dump(), default=str, ensure_ascii=False, indent=2)

    @staticmethod
    def _list_models() -> str:
        models = CostService.get_supported_models()
        return json.dumps(models, ensure_ascii=False, indent=2)

    async def _get_user_summaries(self, params: dict[str, object]) -> str:
        start_str = str(params.get("start_date", "")) if params.get("start_date") else None
        end_str = str(params.get("end_date", "")) if params.get("end_date") else None

        start_date: date | None = None
        end_date: date | None = None
        if start_str:
            start_date = datetime.strptime(start_str, "%Y-%m-%d").date()
        if end_str:
            end_date = datetime.strptime(end_str, "%Y-%m-%d").date()

        async with async_session_factory() as session:
            repo = CostRepository(session)
            summaries = await self._service.get_user_summaries(
                repo,
                start_date=start_date,
                end_date=end_date,
            )

        return json.dumps(
            [s.model_dump() for s in summaries], default=str, ensure_ascii=False, indent=2
        )
