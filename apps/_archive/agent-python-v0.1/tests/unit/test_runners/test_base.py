"""Unit tests for BaseRunner abstract class."""

from __future__ import annotations

import pytest

from agent.runners.base import BaseRunner


class ConcreteRunner(BaseRunner):
    """BaseRunner'in test icin somut implementasyonu."""

    @property
    def tool_name(self) -> str:
        return "test_tool"

    async def execute(self, action: str, params: dict[str, object]) -> dict[str, object]:  # noqa: ARG002
        if action == "succeed":
            return {"success": True, "data": "ok"}
        if action == "fail":
            msg = "Simulated failure"
            raise RuntimeError(msg)
        return {"success": False, "error": f"Unknown action: {action}"}


class FailingToolNameRunner(BaseRunner):
    """tool_name property'si olmayan somut test sinifi yok - abc bunu zorlar."""


class TestBaseRunnerAbstract:
    """BaseRunner abstract sinif testleri."""

    def test_cannot_instantiate_without_tool_name(self) -> None:
        """BaseRunner abstract metotlari olmadan instantiate edilemez."""
        with pytest.raises(TypeError):
            BaseRunner()  # type: ignore[abstract]

    def test_concrete_runner_has_tool_name(self) -> None:
        """Somut runner tool_name dondurur."""
        runner = ConcreteRunner()
        assert runner.tool_name == "test_tool"


class TestBaseRunnerRun:
    """BaseRunner.run() metod testleri."""

    async def test_run_adds_execution_time(self) -> None:
        """run() sonuca execution_time_ms ekler."""
        runner = ConcreteRunner()
        result = await runner.run("succeed", {})
        assert "execution_time_ms" in result
        assert isinstance(result["execution_time_ms"], int)
        assert result["execution_time_ms"] >= 0

    async def test_run_preserves_result_data(self) -> None:
        """run() execute sonucunu korur."""
        runner = ConcreteRunner()
        result = await runner.run("succeed", {})
        assert result["success"] is True
        assert result["data"] == "ok"

    async def test_run_propagates_exception(self) -> None:
        """run() execute'dan gelen exception'i propagate eder."""
        runner = ConcreteRunner()
        with pytest.raises(RuntimeError, match="Simulated failure"):
            await runner.run("fail", {})

    async def test_run_with_unknown_action(self) -> None:
        """run() bilinmeyen aksiyon icin execute sonucunu dondurur."""
        runner = ConcreteRunner()
        result = await runner.run("unknown", {})
        assert result["success"] is False
        assert "Unknown action" in str(result.get("error", ""))
