"""Unit tests for agent.testing.mobile.reporter."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

from agent.testing.mobile.models import (
    MaestroFlowResult,
    MaestroScreenshotInfo,
    MaestroSuiteReport,
    MaestroTestPlatform,
)
from agent.testing.mobile.reporter import MaestroReporter


def _make_suite_report(
    suite_name: str = "test-suite",
    all_passed: bool = True,
    flow_count: int = 1,
) -> MaestroSuiteReport:
    """Test icin suite raporu olusturur."""
    flow_results: list[MaestroFlowResult] = []
    for i in range(flow_count):
        success = all_passed or (i % 2 == 0)
        flow_results.append(
            MaestroFlowResult(
                flow_name=f"flow-{i + 1}",
                flow_file=f"flow-{i + 1}.yaml",
                platform=MaestroTestPlatform.IOS,
                success=success,
                total_tests=3,
                passed_tests=3 if success else 1,
                failed_tests=0 if success else 2,
                duration_ms=1000,
                screenshots=[
                    MaestroScreenshotInfo(
                        flow_name=f"flow-{i + 1}",
                        url=f"https://s3.example.com/ss-{i + 1}.png",
                    ),
                ]
                if success
                else [],
            ),
        )

    passed_flows = sum(1 for r in flow_results if r.success)
    return MaestroSuiteReport(
        suite_name=suite_name,
        total_flows=flow_count,
        passed_flows=passed_flows,
        failed_flows=flow_count - passed_flows,
        total_tests=sum(r.total_tests for r in flow_results),
        passed_tests=sum(r.passed_tests for r in flow_results),
        failed_tests=sum(r.failed_tests for r in flow_results),
        total_duration_ms=sum(r.duration_ms for r in flow_results),
        flow_results=flow_results,
        all_passed=all_passed,
    )


# --- Format Tests ---


class TestFormatFlowText:
    """MaestroReporter.format_flow_text testleri."""

    def test_success_flow(self) -> None:
        reporter = MaestroReporter()
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
        text = reporter.format_flow_text(result)
        assert "Login" in text
        assert "PASSED" in text
        assert "5/5" in text
        assert "1200ms" in text

    def test_failure_flow(self) -> None:
        reporter = MaestroReporter()
        result = MaestroFlowResult(
            flow_name="Checkout",
            flow_file="checkout.yaml",
            platform=MaestroTestPlatform.IOS,
            success=False,
            error="Element not found",
        )
        text = reporter.format_flow_text(result)
        assert "FAILED" in text
        assert "Element not found" in text

    def test_timeout_flow(self) -> None:
        reporter = MaestroReporter()
        result = MaestroFlowResult(
            flow_name="Slow",
            flow_file="slow.yaml",
            platform=MaestroTestPlatform.IOS,
            success=False,
            timed_out=True,
        )
        text = reporter.format_flow_text(result)
        assert "Zaman Asimi" in text

    def test_flow_with_screenshots(self) -> None:
        reporter = MaestroReporter()
        result = MaestroFlowResult(
            flow_name="Test",
            flow_file="test.yaml",
            platform=MaestroTestPlatform.IOS,
            success=True,
            screenshots=[
                MaestroScreenshotInfo(
                    flow_name="Test",
                    url="https://s3.example.com/ss.png",
                ),
            ],
        )
        text = reporter.format_flow_text(result)
        assert "Screenshot sayisi: 1" in text
        assert "s3.example.com" in text


class TestFormatSuiteText:
    """MaestroReporter.format_suite_text testleri."""

    def test_all_passed_suite(self) -> None:
        reporter = MaestroReporter()
        report = _make_suite_report(all_passed=True, flow_count=2)
        text = reporter.format_suite_text(report)
        assert "PASSED" in text
        assert "test-suite" in text
        assert "Toplam Flow: 2" in text

    def test_failed_suite(self) -> None:
        reporter = MaestroReporter()
        report = _make_suite_report(all_passed=False, flow_count=3)
        text = reporter.format_suite_text(report)
        assert "FAILED" in text


class TestFormatSuiteJson:
    """MaestroReporter.format_suite_json testleri."""

    def test_valid_json_output(self) -> None:
        reporter = MaestroReporter()
        report = _make_suite_report()
        json_str = reporter.format_suite_json(report)
        data = json.loads(json_str)
        assert data["suite_name"] == "test-suite"
        assert data["all_passed"] is True

    def test_includes_flow_results(self) -> None:
        reporter = MaestroReporter()
        report = _make_suite_report(flow_count=2)
        json_str = reporter.format_suite_json(report)
        data = json.loads(json_str)
        assert len(data["flow_results"]) == 2


# --- Save Tests ---


class TestSaveReport:
    """MaestroReporter.save_report testleri."""

    def test_save_json_report(self, tmp_path: Path) -> None:
        reporter = MaestroReporter(report_dir=tmp_path)
        report = _make_suite_report()
        file_path = reporter.save_report(report, "test-report", "json")
        assert file_path is not None
        assert file_path.exists()
        assert file_path.suffix == ".json"
        data = json.loads(file_path.read_text(encoding="utf-8"))
        assert data["suite_name"] == "test-suite"

    def test_save_text_report(self, tmp_path: Path) -> None:
        reporter = MaestroReporter(report_dir=tmp_path)
        report = _make_suite_report()
        file_path = reporter.save_report(report, "test-report", "text")
        assert file_path is not None
        assert file_path.exists()
        assert file_path.suffix == ".txt"
        content = file_path.read_text(encoding="utf-8")
        assert "test-suite" in content

    def test_save_without_report_dir_returns_none(self) -> None:
        reporter = MaestroReporter()
        report = _make_suite_report()
        result = reporter.save_report(report, "test")
        assert result is None

    def test_save_creates_directory(self, tmp_path: Path) -> None:
        nested_dir = tmp_path / "a" / "b" / "c"
        reporter = MaestroReporter(report_dir=nested_dir)
        report = _make_suite_report()
        file_path = reporter.save_report(report, "test", "json")
        assert file_path is not None
        assert nested_dir.exists()


# --- Upload Tests ---


class TestUploadReport:
    """MaestroReporter.upload_report testleri."""

    async def test_upload_without_uploader_returns_none(self) -> None:
        reporter = MaestroReporter()
        report = _make_suite_report()
        result = await reporter.upload_report(report, "reports/test.json")
        assert result is None

    async def test_upload_success(self) -> None:
        mock_uploader = AsyncMock()
        mock_result = AsyncMock()
        mock_result.url = "https://s3.example.com/reports/test.json"
        mock_uploader.upload_bytes = AsyncMock(return_value=mock_result)

        reporter = MaestroReporter(s3_uploader=mock_uploader)
        report = _make_suite_report()
        url = await reporter.upload_report(report, "reports/test.json")

        assert url == "https://s3.example.com/reports/test.json"
        mock_uploader.upload_bytes.assert_called_once()

    async def test_upload_failure_returns_none(self) -> None:
        mock_uploader = AsyncMock()
        mock_uploader.upload_bytes = AsyncMock(side_effect=RuntimeError("S3 error"))

        reporter = MaestroReporter(s3_uploader=mock_uploader)
        report = _make_suite_report()
        url = await reporter.upload_report(report, "reports/test.json")

        assert url is None


# --- Summary Tests ---


class TestGenerateSummary:
    """MaestroReporter.generate_summary testleri."""

    def test_all_passed_summary(self) -> None:
        reporter = MaestroReporter()
        report = _make_suite_report(all_passed=True, flow_count=3)
        summary = reporter.generate_summary(report)
        assert summary["overall_status"] == "PASSED"
        assert summary["total_flows"] == 3
        assert summary["passed_flows"] == 3
        assert summary["failed_flows"] == 0
        assert summary["failed_flow_names"] == []
        assert summary["total_screenshots"] == 3

    def test_failed_summary(self) -> None:
        reporter = MaestroReporter()
        report = _make_suite_report(all_passed=False, flow_count=2)
        summary = reporter.generate_summary(report)
        assert summary["overall_status"] == "FAILED"
        assert len(summary["failed_flow_names"]) > 0  # type: ignore[arg-type]
