"""Unit tests for agent.testing.mobile.models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent.testing.mobile.models import (
    MaestroFlowConfig,
    MaestroFlowResult,
    MaestroScreenshotInfo,
    MaestroSuiteConfig,
    MaestroSuiteReport,
    MaestroTestPlatform,
)

# --- MaestroTestPlatform Tests ---


class TestMaestroTestPlatform:
    """MaestroTestPlatform enum testleri."""

    def test_ios_value(self) -> None:
        assert MaestroTestPlatform.IOS == "ios"

    def test_android_value(self) -> None:
        assert MaestroTestPlatform.ANDROID == "android"

    def test_from_string(self) -> None:
        assert MaestroTestPlatform("ios") == MaestroTestPlatform.IOS


# --- MaestroFlowConfig Tests ---


class TestMaestroFlowConfig:
    """MaestroFlowConfig model testleri."""

    def test_create_with_defaults(self) -> None:
        config = MaestroFlowConfig(
            name="Login Flow",
            flow_file="flows/login.yaml",
        )
        assert config.name == "Login Flow"
        assert config.flow_file == "flows/login.yaml"
        assert config.platform == MaestroTestPlatform.IOS
        assert config.timeout == 300
        assert config.cwd is None
        assert config.project_slug is None
        assert config.tags == []

    def test_create_with_all_fields(self) -> None:
        config = MaestroFlowConfig(
            name="Checkout",
            flow_file="flows/checkout.yaml",
            platform=MaestroTestPlatform.ANDROID,
            timeout=120,
            cwd="/app",
            project_slug="my-proj",
            tags=["critical"],
        )
        assert config.platform == MaestroTestPlatform.ANDROID
        assert config.timeout == 120
        assert config.cwd == "/app"

    def test_frozen(self) -> None:
        config = MaestroFlowConfig(name="Test", flow_file="t.yaml")
        with pytest.raises(ValidationError):
            config.name = "Changed"  # type: ignore[misc]

    def test_timeout_min_boundary(self) -> None:
        config = MaestroFlowConfig(name="T", flow_file="t.yaml", timeout=10)
        assert config.timeout == 10

    def test_timeout_below_min_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MaestroFlowConfig(name="T", flow_file="t.yaml", timeout=5)

    def test_timeout_above_max_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MaestroFlowConfig(name="T", flow_file="t.yaml", timeout=601)


# --- MaestroSuiteConfig Tests ---


class TestMaestroSuiteConfig:
    """MaestroSuiteConfig model testleri."""

    def test_create_with_defaults(self) -> None:
        config = MaestroSuiteConfig()
        assert config.suite_name == "default"
        assert config.flows == []
        assert config.stop_on_failure is False

    def test_create_with_flows(self) -> None:
        flows = [
            MaestroFlowConfig(name="A", flow_file="a.yaml"),
            MaestroFlowConfig(name="B", flow_file="b.yaml"),
        ]
        config = MaestroSuiteConfig(
            suite_name="smoke",
            flows=flows,
            stop_on_failure=True,
        )
        assert config.suite_name == "smoke"
        assert len(config.flows) == 2
        assert config.stop_on_failure is True

    def test_frozen(self) -> None:
        config = MaestroSuiteConfig()
        with pytest.raises(ValidationError):
            config.suite_name = "Changed"  # type: ignore[misc]


# --- MaestroScreenshotInfo Tests ---


class TestMaestroScreenshotInfo:
    """MaestroScreenshotInfo model testleri."""

    def test_create_with_url(self) -> None:
        ss = MaestroScreenshotInfo(
            flow_name="Login",
            url="https://s3.example.com/ss.png",
        )
        assert ss.flow_name == "Login"
        assert ss.url == "https://s3.example.com/ss.png"
        assert ss.path is None
        assert ss.timestamp != ""

    def test_create_with_path(self) -> None:
        ss = MaestroScreenshotInfo(
            flow_name="Login",
            path="/tmp/screenshot.png",
        )
        assert ss.path == "/tmp/screenshot.png"
        assert ss.url is None

    def test_frozen(self) -> None:
        ss = MaestroScreenshotInfo(flow_name="Test")
        with pytest.raises(ValidationError):
            ss.flow_name = "Changed"  # type: ignore[misc]


# --- MaestroFlowResult Tests ---


class TestMaestroFlowResult:
    """MaestroFlowResult model testleri."""

    def test_create_success_result(self) -> None:
        result = MaestroFlowResult(
            flow_name="Login",
            flow_file="login.yaml",
            platform=MaestroTestPlatform.IOS,
            success=True,
            total_tests=5,
            passed_tests=5,
            failed_tests=0,
            duration_ms=1200,
        )
        assert result.success is True
        assert result.total_tests == 5
        assert result.error is None
        assert result.timed_out is False

    def test_create_failure_result(self) -> None:
        result = MaestroFlowResult(
            flow_name="Checkout",
            flow_file="checkout.yaml",
            platform=MaestroTestPlatform.ANDROID,
            success=False,
            error="Element not found",
        )
        assert result.success is False
        assert result.error == "Element not found"

    def test_create_timeout_result(self) -> None:
        result = MaestroFlowResult(
            flow_name="Test",
            flow_file="test.yaml",
            platform=MaestroTestPlatform.IOS,
            success=False,
            timed_out=True,
        )
        assert result.timed_out is True

    def test_with_screenshots(self) -> None:
        screenshots = [
            MaestroScreenshotInfo(
                flow_name="Login",
                url="https://s3.example.com/ss1.png",
            ),
        ]
        result = MaestroFlowResult(
            flow_name="Login",
            flow_file="login.yaml",
            platform=MaestroTestPlatform.IOS,
            success=True,
            screenshots=screenshots,
        )
        assert len(result.screenshots) == 1

    def test_frozen(self) -> None:
        result = MaestroFlowResult(
            flow_name="T",
            flow_file="t.yaml",
            platform=MaestroTestPlatform.IOS,
            success=True,
        )
        with pytest.raises(ValidationError):
            result.success = False  # type: ignore[misc]


# --- MaestroSuiteReport Tests ---


class TestMaestroSuiteReport:
    """MaestroSuiteReport model testleri."""

    def test_create_all_passed(self) -> None:
        report = MaestroSuiteReport(
            suite_name="smoke",
            total_flows=2,
            passed_flows=2,
            failed_flows=0,
            total_tests=8,
            passed_tests=8,
            failed_tests=0,
            total_duration_ms=3000,
            all_passed=True,
        )
        assert report.all_passed is True
        assert report.generated_at != ""

    def test_create_with_failures(self) -> None:
        report = MaestroSuiteReport(
            suite_name="e2e",
            total_flows=3,
            passed_flows=2,
            failed_flows=1,
            all_passed=False,
        )
        assert report.all_passed is False

    def test_create_with_flow_results(self) -> None:
        flow_results = [
            MaestroFlowResult(
                flow_name="A",
                flow_file="a.yaml",
                platform=MaestroTestPlatform.IOS,
                success=True,
            ),
            MaestroFlowResult(
                flow_name="B",
                flow_file="b.yaml",
                platform=MaestroTestPlatform.IOS,
                success=False,
                error="Failed",
            ),
        ]
        report = MaestroSuiteReport(
            suite_name="full",
            total_flows=2,
            passed_flows=1,
            failed_flows=1,
            flow_results=flow_results,
            all_passed=False,
        )
        assert len(report.flow_results) == 2

    def test_frozen(self) -> None:
        report = MaestroSuiteReport(
            suite_name="test",
            total_flows=0,
            passed_flows=0,
            failed_flows=0,
        )
        with pytest.raises(ValidationError):
            report.suite_name = "Changed"  # type: ignore[misc]

    def test_defaults(self) -> None:
        report = MaestroSuiteReport(
            suite_name="test",
            total_flows=0,
            passed_flows=0,
            failed_flows=0,
        )
        assert report.total_tests == 0
        assert report.passed_tests == 0
        assert report.failed_tests == 0
        assert report.total_duration_ms == 0
        assert report.flow_results == []
        assert report.all_passed is False
