"""Unit tests for agent.testing.mobile.orchestrator."""

from __future__ import annotations

from unittest.mock import AsyncMock

from agent.testing.mobile.models import (
    MaestroFlowConfig,
    MaestroSuiteConfig,
)
from agent.testing.mobile.orchestrator import (
    MaestroTestOrchestrator,
    _build_flow_result,
    _extract_int,
)

# --- Helper Tests ---


class TestExtractInt:
    """_extract_int testleri."""

    def test_int_value(self) -> None:
        assert _extract_int(42) == 42

    def test_float_value(self) -> None:
        assert _extract_int(3.7) == 3

    def test_string_value(self) -> None:
        assert _extract_int("10") == 10

    def test_invalid_string(self) -> None:
        assert _extract_int("abc") == 0
        assert _extract_int("xyz", 5) == 5

    def test_none_returns_default(self) -> None:
        assert _extract_int(None) == 0

    def test_list_returns_default(self) -> None:
        assert _extract_int([]) == 0


class TestBuildFlowResult:
    """_build_flow_result testleri."""

    def test_success_result(self) -> None:
        config = MaestroFlowConfig(name="Login", flow_file="login.yaml")
        runner_result: dict[str, object] = {
            "success": True,
            "total_tests": 3,
            "passed_tests": 3,
            "failed_tests": 0,
            "output": "Tests passed",
        }
        result = _build_flow_result(config, runner_result, 1000)
        assert result.flow_name == "Login"
        assert result.success is True
        assert result.total_tests == 3
        assert result.duration_ms == 1000
        assert result.raw_output == "Tests passed"

    def test_failure_result(self) -> None:
        config = MaestroFlowConfig(name="Cart", flow_file="cart.yaml")
        runner_result: dict[str, object] = {
            "success": False,
            "error": "Element not found",
        }
        result = _build_flow_result(config, runner_result, 500)
        assert result.success is False
        assert result.error == "Element not found"

    def test_with_screenshots_urls(self) -> None:
        config = MaestroFlowConfig(name="Test", flow_file="t.yaml")
        runner_result: dict[str, object] = {
            "success": True,
            "screenshots": ["https://s3.example.com/ss1.png"],
        }
        result = _build_flow_result(config, runner_result, 300)
        assert len(result.screenshots) == 1
        assert result.screenshots[0].url == "https://s3.example.com/ss1.png"

    def test_with_screenshot_path_fallback(self) -> None:
        config = MaestroFlowConfig(name="Test", flow_file="t.yaml")
        runner_result: dict[str, object] = {
            "success": True,
            "screenshot_path": "/tmp/ss.png",
        }
        result = _build_flow_result(config, runner_result, 200)
        assert len(result.screenshots) == 1
        assert result.screenshots[0].path == "/tmp/ss.png"

    def test_timeout_result(self) -> None:
        config = MaestroFlowConfig(name="Slow", flow_file="slow.yaml")
        runner_result: dict[str, object] = {
            "success": False,
            "timed_out": True,
            "error": "Command timed out",
        }
        result = _build_flow_result(config, runner_result, 60000)
        assert result.timed_out is True
        assert result.success is False


# --- MaestroTestOrchestrator Tests ---


class TestMaestroTestOrchestratorRunFlow:
    """MaestroTestOrchestrator.run_flow testleri."""

    async def test_success_flow(self) -> None:
        mock_runner = AsyncMock()
        mock_runner.execute = AsyncMock(
            return_value={
                "success": True,
                "total_tests": 2,
                "passed_tests": 2,
                "failed_tests": 0,
                "output": "OK",
            },
        )

        orchestrator = MaestroTestOrchestrator(mock_runner)
        config = MaestroFlowConfig(name="Login", flow_file="login.yaml")
        result = await orchestrator.run_flow(config)

        assert result.success is True
        assert result.flow_name == "Login"
        assert result.passed_tests == 2
        mock_runner.execute.assert_called_once_with(
            "run_flow",
            {
                "flow_file": "login.yaml",
                "platform": "ios",
                "timeout": 300,
            },
        )

    async def test_failure_flow(self) -> None:
        mock_runner = AsyncMock()
        mock_runner.execute = AsyncMock(
            return_value={
                "success": False,
                "error": "Element not found",
            },
        )

        orchestrator = MaestroTestOrchestrator(mock_runner)
        config = MaestroFlowConfig(name="Cart", flow_file="cart.yaml")
        result = await orchestrator.run_flow(config)

        assert result.success is False
        assert result.error == "Element not found"

    async def test_exception_handling(self) -> None:
        mock_runner = AsyncMock()
        mock_runner.execute = AsyncMock(side_effect=RuntimeError("Connection lost"))

        orchestrator = MaestroTestOrchestrator(mock_runner)
        config = MaestroFlowConfig(name="Test", flow_file="test.yaml")
        result = await orchestrator.run_flow(config)

        assert result.success is False
        assert "Connection lost" in (result.error or "")

    async def test_flow_with_cwd_and_project_slug(self) -> None:
        mock_runner = AsyncMock()
        mock_runner.execute = AsyncMock(return_value={"success": True})

        orchestrator = MaestroTestOrchestrator(mock_runner)
        config = MaestroFlowConfig(
            name="Test",
            flow_file="test.yaml",
            cwd="/app/flows",
            project_slug="my-proj",
        )
        await orchestrator.run_flow(config)

        call_args = mock_runner.execute.call_args
        params = call_args[0][1]
        assert params["cwd"] == "/app/flows"
        assert params["project_slug"] == "my-proj"


class TestMaestroTestOrchestratorRunSuite:
    """MaestroTestOrchestrator.run_suite testleri."""

    async def test_all_flows_pass(self) -> None:
        mock_runner = AsyncMock()
        mock_runner.execute = AsyncMock(
            return_value={
                "success": True,
                "total_tests": 1,
                "passed_tests": 1,
                "failed_tests": 0,
            },
        )

        orchestrator = MaestroTestOrchestrator(mock_runner)
        suite_config = MaestroSuiteConfig(
            suite_name="smoke",
            flows=[
                MaestroFlowConfig(name="A", flow_file="a.yaml"),
                MaestroFlowConfig(name="B", flow_file="b.yaml"),
            ],
        )
        report = await orchestrator.run_suite(suite_config)

        assert report.all_passed is True
        assert report.total_flows == 2
        assert report.passed_flows == 2
        assert report.failed_flows == 0

    async def test_some_flows_fail(self) -> None:
        call_count = 0

        async def side_effect(
            _action: str,
            _params: dict[str, object],
        ) -> dict[str, object]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"success": True, "total_tests": 1, "passed_tests": 1, "failed_tests": 0}
            return {"success": False, "error": "Failed"}

        mock_runner = AsyncMock()
        mock_runner.execute = AsyncMock(side_effect=side_effect)

        orchestrator = MaestroTestOrchestrator(mock_runner)
        suite_config = MaestroSuiteConfig(
            suite_name="full",
            flows=[
                MaestroFlowConfig(name="A", flow_file="a.yaml"),
                MaestroFlowConfig(name="B", flow_file="b.yaml"),
            ],
        )
        report = await orchestrator.run_suite(suite_config)

        assert report.all_passed is False
        assert report.passed_flows == 1
        assert report.failed_flows == 1

    async def test_stop_on_failure(self) -> None:
        mock_runner = AsyncMock()
        mock_runner.execute = AsyncMock(
            return_value={"success": False, "error": "Failed"},
        )

        orchestrator = MaestroTestOrchestrator(mock_runner)
        suite_config = MaestroSuiteConfig(
            suite_name="strict",
            flows=[
                MaestroFlowConfig(name="A", flow_file="a.yaml"),
                MaestroFlowConfig(name="B", flow_file="b.yaml"),
                MaestroFlowConfig(name="C", flow_file="c.yaml"),
            ],
            stop_on_failure=True,
        )
        report = await orchestrator.run_suite(suite_config)

        # Sadece 1 flow calismali (ilk basarisiz olunca durur)
        assert report.total_flows == 1
        assert report.failed_flows == 1
        mock_runner.execute.assert_called_once()

    async def test_empty_suite(self) -> None:
        mock_runner = AsyncMock()

        orchestrator = MaestroTestOrchestrator(mock_runner)
        suite_config = MaestroSuiteConfig(suite_name="empty")
        report = await orchestrator.run_suite(suite_config)

        assert report.total_flows == 0
        assert report.all_passed is False
        mock_runner.execute.assert_not_called()

    async def test_aggregates_test_counts(self) -> None:
        call_count = 0

        async def side_effect(
            _action: str,
            _params: dict[str, object],
        ) -> dict[str, object]:
            nonlocal call_count
            call_count += 1
            return {
                "success": True,
                "total_tests": call_count * 2,
                "passed_tests": call_count * 2,
                "failed_tests": 0,
            }

        mock_runner = AsyncMock()
        mock_runner.execute = AsyncMock(side_effect=side_effect)

        orchestrator = MaestroTestOrchestrator(mock_runner)
        suite_config = MaestroSuiteConfig(
            suite_name="big",
            flows=[
                MaestroFlowConfig(name="A", flow_file="a.yaml"),
                MaestroFlowConfig(name="B", flow_file="b.yaml"),
            ],
        )
        report = await orchestrator.run_suite(suite_config)

        assert report.total_tests == 6  # 2 + 4
        assert report.passed_tests == 6
