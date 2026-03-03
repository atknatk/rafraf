"""Unit tests for Maestro mobile test integration schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.maestro import (
    FlowFileInfo,
    FlowResult,
    FlowStepScreenshot,
    ListFlowsResponse,
    MaestroFlowDefinition,
    MaestroFlowStatus,
    MaestroPlatform,
    MaestroRunStatus,
    MaestroTestReport,
    RunAllFlowsRequest,
    RunFlowRequest,
    RunFlowResponse,
    RunSuiteRequest,
    ScreenshotResponse,
    SuiteResult,
    TakeScreenshotRequest,
    ValidateFlowRequest,
    ValidateFlowResponse,
)

# --- Enum Tests ---


class TestMaestroPlatform:
    """MaestroPlatform enum testleri."""

    def test_ios_value(self) -> None:
        assert MaestroPlatform.IOS == "ios"

    def test_android_value(self) -> None:
        assert MaestroPlatform.ANDROID == "android"

    def test_from_string(self) -> None:
        assert MaestroPlatform("ios") == MaestroPlatform.IOS
        assert MaestroPlatform("android") == MaestroPlatform.ANDROID


class TestMaestroFlowStatus:
    """MaestroFlowStatus enum testleri."""

    def test_all_statuses_exist(self) -> None:
        expected = {"pending", "running", "passed", "failed", "error", "timeout"}
        actual = {s.value for s in MaestroFlowStatus}
        assert actual == expected


class TestMaestroRunStatus:
    """MaestroRunStatus enum testleri."""

    def test_all_statuses_exist(self) -> None:
        expected = {"pending", "running", "completed", "failed", "partial"}
        actual = {s.value for s in MaestroRunStatus}
        assert actual == expected


# --- Request Model Tests ---


class TestMaestroFlowDefinition:
    """MaestroFlowDefinition model testleri."""

    def test_create_with_defaults(self) -> None:
        flow = MaestroFlowDefinition(
            name="Login Flow",
            flow_file="flows/login.yaml",
        )
        assert flow.name == "Login Flow"
        assert flow.flow_file == "flows/login.yaml"
        assert flow.platform == MaestroPlatform.IOS
        assert flow.timeout == 300
        assert flow.tags == []

    def test_create_with_all_fields(self) -> None:
        flow = MaestroFlowDefinition(
            name="Checkout",
            flow_file="flows/checkout.yaml",
            platform=MaestroPlatform.ANDROID,
            timeout=600,
            tags=["critical", "e2e"],
        )
        assert flow.platform == MaestroPlatform.ANDROID
        assert flow.timeout == 600
        assert flow.tags == ["critical", "e2e"]

    def test_frozen(self) -> None:
        flow = MaestroFlowDefinition(
            name="Test",
            flow_file="test.yaml",
        )
        with pytest.raises(ValidationError):
            flow.name = "Changed"  # type: ignore[misc]

    def test_timeout_min_boundary(self) -> None:
        flow = MaestroFlowDefinition(
            name="Test",
            flow_file="test.yaml",
            timeout=10,
        )
        assert flow.timeout == 10

    def test_timeout_below_min_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MaestroFlowDefinition(
                name="Test",
                flow_file="test.yaml",
                timeout=5,
            )

    def test_timeout_above_max_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MaestroFlowDefinition(
                name="Test",
                flow_file="test.yaml",
                timeout=601,
            )


class TestRunFlowRequest:
    """RunFlowRequest model testleri."""

    def test_create_minimal(self) -> None:
        req = RunFlowRequest(flow_file="login.yaml")
        assert req.flow_file == "login.yaml"
        assert req.platform == MaestroPlatform.IOS
        assert req.cwd is None
        assert req.timeout == 300
        assert req.project_slug is None

    def test_create_with_all_fields(self) -> None:
        req = RunFlowRequest(
            flow_file="checkout.yaml",
            platform=MaestroPlatform.ANDROID,
            cwd="/app/flows",
            timeout=120,
            project_slug="my-project",
        )
        assert req.cwd == "/app/flows"
        assert req.project_slug == "my-project"


class TestRunSuiteRequest:
    """RunSuiteRequest model testleri."""

    def test_create_minimal(self) -> None:
        req = RunSuiteRequest(
            flows=[
                MaestroFlowDefinition(name="A", flow_file="a.yaml"),
            ],
        )
        assert req.suite_name == "default"
        assert len(req.flows) == 1
        assert req.stop_on_failure is False

    def test_create_with_all_fields(self) -> None:
        req = RunSuiteRequest(
            suite_name="smoke",
            flows=[
                MaestroFlowDefinition(name="A", flow_file="a.yaml"),
                MaestroFlowDefinition(name="B", flow_file="b.yaml"),
            ],
            project_slug="proj",
            cwd="/flows",
            stop_on_failure=True,
        )
        assert req.suite_name == "smoke"
        assert len(req.flows) == 2
        assert req.stop_on_failure is True


class TestRunAllFlowsRequest:
    """RunAllFlowsRequest model testleri."""

    def test_create_minimal(self) -> None:
        req = RunAllFlowsRequest(flows_dir="/app/flows")
        assert req.flows_dir == "/app/flows"
        assert req.platform == MaestroPlatform.IOS

    def test_create_with_all_fields(self) -> None:
        req = RunAllFlowsRequest(
            flows_dir="/flows",
            platform=MaestroPlatform.ANDROID,
            cwd="/app",
            timeout=500,
            project_slug="proj-1",
        )
        assert req.timeout == 500


class TestValidateFlowRequest:
    """ValidateFlowRequest model testleri."""

    def test_create(self) -> None:
        req = ValidateFlowRequest(flow_file="test.yaml")
        assert req.flow_file == "test.yaml"


class TestTakeScreenshotRequest:
    """TakeScreenshotRequest model testleri."""

    def test_defaults(self) -> None:
        req = TakeScreenshotRequest()
        assert req.platform == MaestroPlatform.IOS
        assert req.project_slug is None


# --- Response Model Tests ---


class TestFlowResult:
    """FlowResult model testleri."""

    def test_create_passed(self) -> None:
        result = FlowResult(
            flow_file="login.yaml",
            platform=MaestroPlatform.IOS,
            status=MaestroFlowStatus.PASSED,
            total_tests=5,
            passed_tests=5,
            failed_tests=0,
            duration_ms=1200,
        )
        assert result.status == MaestroFlowStatus.PASSED
        assert result.total_tests == 5
        assert result.error is None

    def test_create_failed(self) -> None:
        result = FlowResult(
            flow_file="checkout.yaml",
            platform=MaestroPlatform.ANDROID,
            status=MaestroFlowStatus.FAILED,
            total_tests=3,
            passed_tests=2,
            failed_tests=1,
            error="Step 3 failed: element not found",
        )
        assert result.failed_tests == 1
        assert result.error is not None

    def test_frozen(self) -> None:
        result = FlowResult(
            flow_file="test.yaml",
            platform=MaestroPlatform.IOS,
            status=MaestroFlowStatus.PASSED,
        )
        with pytest.raises(ValidationError):
            result.status = MaestroFlowStatus.FAILED  # type: ignore[misc]

    def test_with_screenshots(self) -> None:
        result = FlowResult(
            flow_file="test.yaml",
            platform=MaestroPlatform.IOS,
            status=MaestroFlowStatus.PASSED,
            screenshots=["https://s3.example.com/screenshot1.png"],
        )
        assert len(result.screenshots) == 1


class TestRunFlowResponse:
    """RunFlowResponse model testleri."""

    def test_success_response(self) -> None:
        flow_result = FlowResult(
            flow_file="test.yaml",
            platform=MaestroPlatform.IOS,
            status=MaestroFlowStatus.PASSED,
        )
        response = RunFlowResponse(success=True, result=flow_result)
        assert response.success is True

    def test_failure_response(self) -> None:
        flow_result = FlowResult(
            flow_file="test.yaml",
            platform=MaestroPlatform.IOS,
            status=MaestroFlowStatus.FAILED,
            error="Timeout",
        )
        response = RunFlowResponse(success=False, result=flow_result)
        assert response.success is False


class TestSuiteResult:
    """SuiteResult model testleri."""

    def test_create_completed(self) -> None:
        result = SuiteResult(
            suite_name="smoke",
            status=MaestroRunStatus.COMPLETED,
            total_flows=3,
            passed_flows=3,
            failed_flows=0,
            total_tests=10,
            passed_tests=10,
            failed_tests=0,
            duration_ms=5000,
        )
        assert result.status == MaestroRunStatus.COMPLETED
        assert result.failed_flows == 0

    def test_create_partial(self) -> None:
        result = SuiteResult(
            suite_name="full",
            status=MaestroRunStatus.PARTIAL,
            total_flows=5,
            passed_flows=3,
            failed_flows=2,
        )
        assert result.status == MaestroRunStatus.PARTIAL


class TestValidateFlowResponse:
    """ValidateFlowResponse model testleri."""

    def test_valid_flow(self) -> None:
        resp = ValidateFlowResponse(
            valid=True,
            flow_file="test.yaml",
            file_size_bytes=256,
            has_known_commands=True,
        )
        assert resp.valid is True
        assert resp.has_known_commands is True

    def test_invalid_flow(self) -> None:
        resp = ValidateFlowResponse(
            valid=False,
            flow_file="bad.yaml",
            error="Empty file",
        )
        assert resp.valid is False
        assert resp.error == "Empty file"


class TestScreenshotResponse:
    """ScreenshotResponse model testleri."""

    def test_success_with_url(self) -> None:
        resp = ScreenshotResponse(
            success=True,
            screenshot_url="https://s3.example.com/ss.png",
            platform=MaestroPlatform.IOS,
        )
        assert resp.success is True
        assert resp.screenshot_url is not None

    def test_failure(self) -> None:
        resp = ScreenshotResponse(
            success=False,
            platform=MaestroPlatform.IOS,
            error="xcrun not found",
        )
        assert resp.success is False


class TestFlowFileInfo:
    """FlowFileInfo model testleri."""

    def test_create(self) -> None:
        info = FlowFileInfo(
            name="login.yaml",
            path="/flows/login.yaml",
            size_bytes=1024,
        )
        assert info.name == "login.yaml"
        assert info.size_bytes == 1024


class TestListFlowsResponse:
    """ListFlowsResponse model testleri."""

    def test_success_response(self) -> None:
        resp = ListFlowsResponse(
            success=True,
            flows_dir="/flows",
            flow_count=2,
            flows=[
                FlowFileInfo(name="a.yaml", path="/flows/a.yaml", size_bytes=100),
                FlowFileInfo(name="b.yaml", path="/flows/b.yaml", size_bytes=200),
            ],
        )
        assert resp.flow_count == 2
        assert len(resp.flows) == 2


class TestFlowStepScreenshot:
    """FlowStepScreenshot model testleri."""

    def test_create(self) -> None:
        ss = FlowStepScreenshot(
            step_name="login-step-1",
            screenshot_url="https://s3.example.com/ss.png",
        )
        assert ss.step_name == "login-step-1"
        assert ss.timestamp != ""


class TestMaestroTestReport:
    """MaestroTestReport model testleri."""

    def test_create_minimal(self) -> None:
        report = MaestroTestReport(
            run_id="abc-123",
            suite_name="smoke",
            status=MaestroRunStatus.COMPLETED,
            total_flows=1,
            passed_flows=1,
            failed_flows=0,
        )
        assert report.run_id == "abc-123"
        assert report.generated_at != ""

    def test_create_with_screenshots(self) -> None:
        report = MaestroTestReport(
            run_id="def-456",
            suite_name="e2e",
            status=MaestroRunStatus.PARTIAL,
            total_flows=2,
            passed_flows=1,
            failed_flows=1,
            screenshots=[
                FlowStepScreenshot(
                    step_name="step-1",
                    screenshot_url="https://s3.example.com/ss1.png",
                ),
            ],
        )
        assert len(report.screenshots) == 1

    def test_frozen(self) -> None:
        report = MaestroTestReport(
            run_id="id",
            suite_name="test",
            status=MaestroRunStatus.COMPLETED,
            total_flows=0,
            passed_flows=0,
            failed_flows=0,
        )
        with pytest.raises(ValidationError):
            report.run_id = "changed"  # type: ignore[misc]
