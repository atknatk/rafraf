"""Unit tests for MaestroService."""

from __future__ import annotations

from app.schemas.maestro import (
    MaestroFlowDefinition,
    MaestroFlowStatus,
    MaestroPlatform,
    MaestroRunStatus,
    RunSuiteResponse,
)
from app.services.maestro_service import (
    MaestroService,
    _build_flow_result,
    _determine_flow_status,
    _determine_suite_status,
    _extract_int,
)

# --- Helper Function Tests ---


class TestDetermineFlowStatus:
    """_determine_flow_status testleri."""

    def test_timeout_returns_timeout(self) -> None:
        result: dict[str, object] = {"timed_out": True}
        assert _determine_flow_status(result) == MaestroFlowStatus.TIMEOUT

    def test_error_returns_error(self) -> None:
        result: dict[str, object] = {"error": "Something broke", "success": False}
        assert _determine_flow_status(result) == MaestroFlowStatus.ERROR

    def test_success_no_failures_returns_passed(self) -> None:
        result: dict[str, object] = {"success": True, "failed_tests": 0}
        assert _determine_flow_status(result) == MaestroFlowStatus.PASSED

    def test_success_with_failures_returns_failed(self) -> None:
        result: dict[str, object] = {"success": True, "failed_tests": 2}
        assert _determine_flow_status(result) == MaestroFlowStatus.FAILED

    def test_not_success_returns_failed(self) -> None:
        result: dict[str, object] = {"success": False}
        assert _determine_flow_status(result) == MaestroFlowStatus.FAILED

    def test_empty_result_returns_failed(self) -> None:
        result: dict[str, object] = {}
        assert _determine_flow_status(result) == MaestroFlowStatus.FAILED

    def test_timeout_takes_priority_over_error(self) -> None:
        result: dict[str, object] = {
            "timed_out": True,
            "error": "timeout error",
            "success": False,
        }
        assert _determine_flow_status(result) == MaestroFlowStatus.TIMEOUT


class TestDetermineSuiteStatus:
    """_determine_suite_status testleri."""

    def test_empty_results_returns_failed(self) -> None:

        assert _determine_suite_status([]) == MaestroRunStatus.FAILED

    def test_all_passed_returns_completed(self) -> None:
        from app.schemas.maestro import FlowResult

        results = [
            FlowResult(
                flow_file="a.yaml",
                platform=MaestroPlatform.IOS,
                status=MaestroFlowStatus.PASSED,
            ),
            FlowResult(
                flow_file="b.yaml",
                platform=MaestroPlatform.IOS,
                status=MaestroFlowStatus.PASSED,
            ),
        ]
        assert _determine_suite_status(results) == MaestroRunStatus.COMPLETED

    def test_all_failed_returns_failed(self) -> None:
        from app.schemas.maestro import FlowResult

        results = [
            FlowResult(
                flow_file="a.yaml",
                platform=MaestroPlatform.IOS,
                status=MaestroFlowStatus.FAILED,
            ),
        ]
        assert _determine_suite_status(results) == MaestroRunStatus.FAILED

    def test_mixed_returns_partial(self) -> None:
        from app.schemas.maestro import FlowResult

        results = [
            FlowResult(
                flow_file="a.yaml",
                platform=MaestroPlatform.IOS,
                status=MaestroFlowStatus.PASSED,
            ),
            FlowResult(
                flow_file="b.yaml",
                platform=MaestroPlatform.IOS,
                status=MaestroFlowStatus.FAILED,
            ),
        ]
        assert _determine_suite_status(results) == MaestroRunStatus.PARTIAL


class TestExtractInt:
    """_extract_int testleri."""

    def test_int_value(self) -> None:
        assert _extract_int(42) == 42

    def test_float_value(self) -> None:
        assert _extract_int(3.7) == 3

    def test_string_value(self) -> None:
        assert _extract_int("10") == 10

    def test_invalid_string_returns_default(self) -> None:
        assert _extract_int("abc") == 0
        assert _extract_int("abc", 99) == 99

    def test_none_returns_default(self) -> None:
        assert _extract_int(None) == 0
        assert _extract_int(None, 5) == 5

    def test_list_returns_default(self) -> None:
        assert _extract_int([1, 2, 3]) == 0


class TestBuildFlowResult:
    """_build_flow_result testleri."""

    def test_success_result(self) -> None:
        runner_result: dict[str, object] = {
            "success": True,
            "total_tests": 5,
            "passed_tests": 5,
            "failed_tests": 0,
            "duration_ms": 1500,
            "output": "All tests passed",
        }
        result = _build_flow_result(runner_result, "login.yaml", "ios")
        assert result.flow_file == "login.yaml"
        assert result.platform == "ios"
        assert result.status == MaestroFlowStatus.PASSED
        assert result.total_tests == 5
        assert result.passed_tests == 5
        assert result.duration_ms == 1500
        assert result.output == "All tests passed"
        assert result.error is None

    def test_failure_result(self) -> None:
        runner_result: dict[str, object] = {
            "success": False,
            "error": "Element not found",
            "output": "",
        }
        result = _build_flow_result(runner_result, "checkout.yaml", "android")
        assert result.status == MaestroFlowStatus.ERROR
        assert result.error == "Element not found"

    def test_timeout_result(self) -> None:
        runner_result: dict[str, object] = {
            "success": False,
            "timed_out": True,
            "error": "Command timed out",
        }
        result = _build_flow_result(runner_result, "test.yaml", "ios")
        assert result.status == MaestroFlowStatus.TIMEOUT
        assert result.timed_out is True

    def test_with_screenshots(self) -> None:
        runner_result: dict[str, object] = {
            "success": True,
            "screenshots": ["https://s3.example.com/ss1.png", "https://s3.example.com/ss2.png"],
        }
        result = _build_flow_result(runner_result, "test.yaml", "ios")
        assert len(result.screenshots) == 2


# --- MaestroService Tests ---


class TestMaestroServiceRunFlow:
    """MaestroService.run_flow testleri."""

    async def test_success_flow(self) -> None:
        service = MaestroService()
        runner_result: dict[str, object] = {
            "success": True,
            "total_tests": 3,
            "passed_tests": 3,
            "failed_tests": 0,
            "duration_ms": 800,
        }
        response = await service.run_flow(
            runner_result=runner_result,
            flow_file="login.yaml",
            platform="ios",
        )
        assert response.success is True
        assert response.result.status == MaestroFlowStatus.PASSED

    async def test_failure_flow(self) -> None:
        service = MaestroService()
        runner_result: dict[str, object] = {
            "success": False,
            "error": "Test failed",
        }
        response = await service.run_flow(
            runner_result=runner_result,
            flow_file="test.yaml",
            platform="ios",
        )
        assert response.success is False
        assert response.result.status == MaestroFlowStatus.ERROR


class TestMaestroServiceRunSuite:
    """MaestroService.run_suite testleri."""

    async def test_all_flows_pass(self) -> None:
        service = MaestroService()
        flows = [
            MaestroFlowDefinition(name="A", flow_file="a.yaml"),
            MaestroFlowDefinition(name="B", flow_file="b.yaml"),
        ]
        results: list[dict[str, object]] = [
            {"success": True, "total_tests": 2, "passed_tests": 2, "failed_tests": 0},
            {"success": True, "total_tests": 3, "passed_tests": 3, "failed_tests": 0},
        ]
        response = await service.run_suite(
            suite_name="smoke",
            flows=flows,
            runner_results=results,
        )
        assert response.success is True
        assert response.result.status == MaestroRunStatus.COMPLETED
        assert response.result.total_flows == 2
        assert response.result.passed_flows == 2

    async def test_some_flows_fail(self) -> None:
        service = MaestroService()
        flows = [
            MaestroFlowDefinition(name="A", flow_file="a.yaml"),
            MaestroFlowDefinition(name="B", flow_file="b.yaml"),
        ]
        results: list[dict[str, object]] = [
            {"success": True, "total_tests": 2, "passed_tests": 2, "failed_tests": 0},
            {"success": False, "error": "Failed"},
        ]
        response = await service.run_suite(
            suite_name="test",
            flows=flows,
            runner_results=results,
        )
        assert response.success is False
        assert response.result.status == MaestroRunStatus.PARTIAL

    async def test_empty_suite(self) -> None:
        service = MaestroService()
        response = await service.run_suite(
            suite_name="empty",
            flows=[],
            runner_results=[],
        )
        assert response.success is False
        assert response.result.status == MaestroRunStatus.FAILED


class TestMaestroServiceValidate:
    """MaestroService.process_validate_result testleri."""

    async def test_valid_result(self) -> None:
        service = MaestroService()
        runner_result: dict[str, object] = {
            "valid": True,
            "flow_file": "test.yaml",
            "file_size_bytes": 512,
            "has_known_commands": True,
        }
        response = await service.process_validate_result(
            runner_result=runner_result,
            flow_file="test.yaml",
        )
        assert response.valid is True
        assert response.has_known_commands is True
        assert response.file_size_bytes == 512

    async def test_invalid_result(self) -> None:
        service = MaestroService()
        runner_result: dict[str, object] = {
            "valid": False,
            "error": "Empty file",
        }
        response = await service.process_validate_result(
            runner_result=runner_result,
            flow_file="bad.yaml",
        )
        assert response.valid is False
        assert response.error == "Empty file"


class TestMaestroServiceScreenshot:
    """MaestroService.process_screenshot_result testleri."""

    async def test_success_with_url(self) -> None:
        service = MaestroService()
        runner_result: dict[str, object] = {
            "success": True,
            "screenshot_url": "https://s3.example.com/ss.png",
            "platform": "ios",
        }
        response = await service.process_screenshot_result(
            runner_result=runner_result,
            platform="ios",
        )
        assert response.success is True
        assert response.screenshot_url == "https://s3.example.com/ss.png"

    async def test_failure(self) -> None:
        service = MaestroService()
        runner_result: dict[str, object] = {
            "success": False,
            "error": "xcrun not found",
        }
        response = await service.process_screenshot_result(
            runner_result=runner_result,
            platform="ios",
        )
        assert response.success is False
        assert response.error == "xcrun not found"


class TestMaestroServiceListFlows:
    """MaestroService.process_list_flows_result testleri."""

    async def test_success_result(self) -> None:
        service = MaestroService()
        runner_result: dict[str, object] = {
            "success": True,
            "flows_dir": "/flows",
            "flow_count": 2,
            "flows": [
                {"name": "a.yaml", "path": "/flows/a.yaml", "size_bytes": 100},
                {"name": "b.yaml", "path": "/flows/b.yaml", "size_bytes": 200},
            ],
        }
        response = await service.process_list_flows_result(
            runner_result=runner_result,
        )
        assert response.success is True
        assert response.flow_count == 2
        assert len(response.flows) == 2

    async def test_empty_result(self) -> None:
        service = MaestroService()
        runner_result: dict[str, object] = {
            "success": False,
            "flows_dir": "/empty",
            "error": "No flows found",
        }
        response = await service.process_list_flows_result(
            runner_result=runner_result,
        )
        assert response.success is False
        assert len(response.flows) == 0


class TestMaestroServiceGenerateReport:
    """MaestroService.generate_test_report testleri."""

    async def test_generates_report(self) -> None:
        from app.schemas.maestro import FlowResult, SuiteResult

        service = MaestroService()
        suite_result = SuiteResult(
            suite_name="smoke",
            status=MaestroRunStatus.COMPLETED,
            total_flows=1,
            passed_flows=1,
            failed_flows=0,
            total_tests=3,
            passed_tests=3,
            failed_tests=0,
            duration_ms=1000,
            flow_results=[
                FlowResult(
                    flow_file="login.yaml",
                    platform=MaestroPlatform.IOS,
                    status=MaestroFlowStatus.PASSED,
                    screenshots=["https://s3.example.com/ss1.png"],
                ),
            ],
        )
        suite_response = RunSuiteResponse(
            success=True,
            result=suite_result,
        )
        report = await service.generate_test_report(
            suite_response=suite_response,
        )
        assert report.run_id != ""
        assert report.suite_name == "smoke"
        assert report.status == MaestroRunStatus.COMPLETED
        assert len(report.screenshots) == 1
        assert report.generated_at != ""
