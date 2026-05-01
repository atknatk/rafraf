"""Unit tests for agent.testing.reporter."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from agent.testing.models import (
    AssertionResult,
    AssertionType,
    StepType,
    TestReport,
    TestStepResult,
    TestSuiteReport,
)
from agent.testing.reporter import TestReporter
from agent.upload.s3_uploader import S3Uploader, UploadResult

# --- Fixtures ---


@pytest.fixture
def reporter(tmp_path: Path) -> TestReporter:
    """TestReporter instance olusturur."""
    return TestReporter(report_dir=tmp_path / "reports")


@pytest.fixture
def reporter_no_dir() -> TestReporter:
    """Dizinsiz TestReporter olusturur."""
    return TestReporter()


@pytest.fixture
def sample_report() -> TestReport:
    """Ornek test raporu olusturur."""
    return TestReport(
        scenario_name="Homepage Test",
        passed=True,
        total_steps=2,
        passed_steps=2,
        failed_steps=0,
        duration_ms=1500,
        step_results=[
            TestStepResult(
                step_name="Load Page",
                step_type=StepType.PAGE_LOAD,
                passed=True,
                duration_ms=800,
                assertion_results=[
                    AssertionResult(
                        assertion_type=AssertionType.STATUS_CODE,
                        passed=True,
                        expected=200,
                        actual=200,
                        message="Status code: beklenen=200, gerceklesen=200",
                    ),
                ],
            ),
            TestStepResult(
                step_name="Check Element",
                step_type=StepType.CHECK_ELEMENT,
                passed=True,
                duration_ms=700,
                screenshot_url="https://s3.amazonaws.com/test.png",
            ),
        ],
        started_at="2026-03-03T12:00:00Z",
        finished_at="2026-03-03T12:00:02Z",
    )


@pytest.fixture
def sample_suite_report(sample_report: TestReport) -> TestSuiteReport:
    """Ornek suite raporu olusturur."""
    return TestSuiteReport(
        suite_name="Smoke Tests",
        total_scenarios=2,
        passed_scenarios=1,
        failed_scenarios=1,
        total_duration_ms=3000,
        scenario_reports=[
            sample_report,
            TestReport(
                scenario_name="Failed Test",
                passed=False,
                total_steps=1,
                passed_steps=0,
                failed_steps=1,
                duration_ms=500,
                error="Page not found",
            ),
        ],
    )


# --- format_report_text Tests ---


class TestFormatReportText:
    """TestReporter.format_report_text() testleri."""

    def test_report_contains_scenario_name(
        self,
        reporter: TestReporter,
        sample_report: TestReport,
    ) -> None:
        """Rapor senaryo adini icerir."""
        text = reporter.format_report_text(sample_report)
        assert "Homepage Test" in text

    def test_report_contains_status(
        self,
        reporter: TestReporter,
        sample_report: TestReport,
    ) -> None:
        """Rapor durum bilgisini icerir."""
        text = reporter.format_report_text(sample_report)
        assert "PASSED" in text

    def test_report_contains_step_details(
        self,
        reporter: TestReporter,
        sample_report: TestReport,
    ) -> None:
        """Rapor adim detaylarini icerir."""
        text = reporter.format_report_text(sample_report)
        assert "Load Page" in text
        assert "Check Element" in text
        assert "[PASS]" in text

    def test_report_contains_assertion_details(
        self,
        reporter: TestReporter,
        sample_report: TestReport,
    ) -> None:
        """Rapor assertion detaylarini icerir."""
        text = reporter.format_report_text(sample_report)
        assert "Status code" in text

    def test_report_contains_screenshot(
        self,
        reporter: TestReporter,
        sample_report: TestReport,
    ) -> None:
        """Rapor screenshot URL'ini icerir."""
        text = reporter.format_report_text(sample_report)
        assert "Screenshot:" in text

    def test_failed_report_shows_fail(
        self,
        reporter: TestReporter,
    ) -> None:
        """Basarisiz rapor FAILED gosterir."""
        failed_report = TestReport(
            scenario_name="Failed",
            passed=False,
            total_steps=1,
            passed_steps=0,
            failed_steps=1,
            duration_ms=100,
            step_results=[
                TestStepResult(
                    step_name="Bad Step",
                    step_type=StepType.PAGE_LOAD,
                    passed=False,
                    error="Connection error",
                ),
            ],
            error="Step failed",
        )
        text = reporter.format_report_text(failed_report)
        assert "FAILED" in text
        assert "[FAIL]" in text
        assert "Connection error" in text


# --- format_suite_report_text Tests ---


class TestFormatSuiteReportText:
    """TestReporter.format_suite_report_text() testleri."""

    def test_suite_report_contains_suite_name(
        self,
        reporter: TestReporter,
        sample_suite_report: TestSuiteReport,
    ) -> None:
        """Suite raporu suite adini icerir."""
        text = reporter.format_suite_report_text(sample_suite_report)
        assert "Smoke Tests" in text

    def test_suite_report_contains_scenario_count(
        self,
        reporter: TestReporter,
        sample_suite_report: TestSuiteReport,
    ) -> None:
        """Suite raporu senaryo sayisini icerir."""
        text = reporter.format_suite_report_text(sample_suite_report)
        assert "Toplam Senaryo: 2" in text

    def test_suite_report_includes_all_scenarios(
        self,
        reporter: TestReporter,
        sample_suite_report: TestSuiteReport,
    ) -> None:
        """Suite raporu tum senaryolari icerir."""
        text = reporter.format_suite_report_text(sample_suite_report)
        assert "Homepage Test" in text
        assert "Failed Test" in text


# --- format_report_json Tests ---


class TestFormatReportJson:
    """TestReporter JSON format testleri."""

    def test_report_json_valid(
        self,
        reporter: TestReporter,
        sample_report: TestReport,
    ) -> None:
        """JSON rapor gecerli JSON."""
        json_str = reporter.format_report_json(sample_report)
        data = json.loads(json_str)
        assert data["scenario_name"] == "Homepage Test"
        assert data["passed"] is True

    def test_suite_report_json_valid(
        self,
        reporter: TestReporter,
        sample_suite_report: TestSuiteReport,
    ) -> None:
        """Suite JSON raporu gecerli JSON."""
        json_str = reporter.format_suite_report_json(sample_suite_report)
        data = json.loads(json_str)
        assert data["suite_name"] == "Smoke Tests"
        assert len(data["scenario_reports"]) == 2


# --- save_report Tests ---


class TestSaveReport:
    """TestReporter.save_report() testleri."""

    def test_save_json_report(
        self,
        reporter: TestReporter,
        sample_report: TestReport,
    ) -> None:
        """JSON rapor dosyaya kaydedilir."""
        path = reporter.save_report(sample_report, "test_report", format_type="json")
        assert path is not None
        assert path.exists()
        assert path.suffix == ".json"

        content = json.loads(path.read_text(encoding="utf-8"))
        assert content["scenario_name"] == "Homepage Test"

    def test_save_text_report(
        self,
        reporter: TestReporter,
        sample_report: TestReport,
    ) -> None:
        """Text rapor dosyaya kaydedilir."""
        path = reporter.save_report(sample_report, "test_report", format_type="text")
        assert path is not None
        assert path.exists()
        assert path.suffix == ".txt"

        content = path.read_text(encoding="utf-8")
        assert "Homepage Test" in content

    def test_save_suite_report(
        self,
        reporter: TestReporter,
        sample_suite_report: TestSuiteReport,
    ) -> None:
        """Suite raporu dosyaya kaydedilir."""
        path = reporter.save_report(
            sample_suite_report,
            "suite_report",
            format_type="json",
        )
        assert path is not None
        assert path.exists()

    def test_save_no_dir_returns_none(
        self,
        reporter_no_dir: TestReporter,
        sample_report: TestReport,
    ) -> None:
        """report_dir yoksa None dondurur."""
        path = reporter_no_dir.save_report(sample_report, "test")
        assert path is None

    def test_save_creates_dir(
        self,
        sample_report: TestReport,
        tmp_path: Path,
    ) -> None:
        """Rapor dizini yoksa olusturulur."""
        deep_dir = tmp_path / "deep" / "nested"
        reporter = TestReporter(report_dir=deep_dir)

        path = reporter.save_report(sample_report, "test", format_type="json")
        assert path is not None
        assert path.exists()


# --- upload_report Tests ---


class TestUploadReport:
    """TestReporter.upload_report() testleri."""

    async def test_upload_no_uploader_returns_none(
        self,
        reporter: TestReporter,
        sample_report: TestReport,
    ) -> None:
        """S3 uploader yoksa None dondurur."""
        url = await reporter.upload_report(sample_report, "reports/test.json")
        assert url is None

    async def test_upload_success(
        self,
        sample_report: TestReport,
    ) -> None:
        """S3'e basariyla yukler."""
        mock_uploader = AsyncMock(spec=S3Uploader)
        mock_uploader.upload_bytes = AsyncMock(
            return_value=UploadResult(
                url="https://test-bucket.s3.eu-west-1.amazonaws.com/reports/test.json",
                key="reports/test.json",
                bucket="test-bucket",
                size_bytes=100,
                content_type="application/json",
                multipart=False,
            ),
        )

        reporter = TestReporter(s3_uploader=mock_uploader)
        url = await reporter.upload_report(sample_report, "reports/test.json")
        assert url is not None
        assert "test-bucket" in url
        mock_uploader.upload_bytes.assert_called_once()

    async def test_upload_failure_returns_none(
        self,
        sample_report: TestReport,
    ) -> None:
        """S3 upload hatasi None dondurur."""
        mock_uploader = AsyncMock(spec=S3Uploader)
        mock_uploader.upload_bytes = AsyncMock(side_effect=Exception("S3 error"))

        reporter = TestReporter(s3_uploader=mock_uploader)
        url = await reporter.upload_report(sample_report, "reports/test.json")
        assert url is None


# --- generate_summary Tests ---


class TestGenerateSummary:
    """TestReporter.generate_summary() testleri."""

    def test_summary_passed(
        self,
        reporter: TestReporter,
    ) -> None:
        """Tum senaryolar basarili ise PASSED."""
        suite = TestSuiteReport(
            suite_name="All Pass",
            total_scenarios=2,
            passed_scenarios=2,
            failed_scenarios=0,
            total_duration_ms=1000,
            scenario_reports=[
                TestReport(
                    scenario_name="S1",
                    passed=True,
                    total_steps=1,
                    passed_steps=1,
                    failed_steps=0,
                    duration_ms=500,
                ),
                TestReport(
                    scenario_name="S2",
                    passed=True,
                    total_steps=2,
                    passed_steps=2,
                    failed_steps=0,
                    duration_ms=500,
                ),
            ],
        )

        summary = reporter.generate_summary(suite)
        assert summary["overall_status"] == "PASSED"
        assert summary["total_steps"] == 3
        assert summary["passed_steps"] == 3
        assert summary["failed_steps"] == 0
        assert summary["failed_scenario_names"] == []

    def test_summary_failed(
        self,
        reporter: TestReporter,
        sample_suite_report: TestSuiteReport,
    ) -> None:
        """Basarisiz senaryolar raporlanir."""
        summary = reporter.generate_summary(sample_suite_report)
        assert summary["overall_status"] == "FAILED"
        assert "Failed Test" in summary["failed_scenario_names"]  # type: ignore[operator]
