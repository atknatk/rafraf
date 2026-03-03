"""Test rapor olusturucu - JSON ve text formatinda rapor uretir.

Test sonuclarini okunabilir formatlarda raporlar:
- JSON: Makine tarafindan islenebilir
- Text: Insan tarafindan okunabilir
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from agent.upload.s3_uploader import S3Uploader

from agent.testing.models import TestReport, TestSuiteReport

logger = structlog.get_logger()


class TestReporter:
    """Test sonuclarini raporlar.

    JSON ve text formatinda rapor uretir. Opsiyonel olarak
    raporlari S3'e yukleyebilir.

    Args:
        s3_uploader: Rapor yukleme icin S3Uploader (opsiyonel).
        report_dir: Lokal rapor dizini (opsiyonel).
    """

    def __init__(
        self,
        s3_uploader: S3Uploader | None = None,
        report_dir: Path | str | None = None,
    ) -> None:
        self._s3_uploader = s3_uploader
        self._report_dir = Path(report_dir) if report_dir else None

    def format_report_text(self, report: TestReport) -> str:
        """Senaryo raporunu okunabilir text formatinda olusturur.

        Args:
            report: Senaryo raporu.

        Returns:
            Formatlanmis text rapor.
        """
        status = "PASSED" if report.passed else "FAILED"
        lines: list[str] = [
            f"{'=' * 60}",
            f"Test Raporu: {report.scenario_name}",
            f"{'=' * 60}",
            f"Durum: {status}",
            f"Toplam Adim: {report.total_steps}",
            f"Basarili: {report.passed_steps}",
            f"Basarisiz: {report.failed_steps}",
            f"Sure: {report.duration_ms}ms",
            f"Baslangic: {report.started_at}",
            f"Bitis: {report.finished_at}",
        ]

        if report.error:
            lines.append(f"Hata: {report.error}")

        lines.append("")
        lines.append("Adim Detaylari:")
        lines.append(f"{'-' * 40}")

        for step_result in report.step_results:
            step_status = "PASS" if step_result.passed else "FAIL"
            lines.append(
                f"  [{step_status}] {step_result.step_name} "
                f"({step_result.step_type}) - {step_result.duration_ms}ms",
            )

            if step_result.error:
                lines.append(f"    Hata: {step_result.error}")

            for ar in step_result.assertion_results:
                ar_status = "PASS" if ar.passed else "FAIL"
                lines.append(f"    [{ar_status}] {ar.message}")

            if step_result.screenshot_url:
                lines.append(f"    Screenshot: {step_result.screenshot_url}")

        lines.append(f"{'=' * 60}")
        return "\n".join(lines)

    def format_suite_report_text(self, suite_report: TestSuiteReport) -> str:
        """Suite raporunu okunabilir text formatinda olusturur.

        Args:
            suite_report: Suite raporu.

        Returns:
            Formatlanmis text rapor.
        """
        lines: list[str] = [
            f"{'#' * 60}",
            f"Test Suite Raporu: {suite_report.suite_name}",
            f"{'#' * 60}",
            f"Toplam Senaryo: {suite_report.total_scenarios}",
            f"Basarili: {suite_report.passed_scenarios}",
            f"Basarisiz: {suite_report.failed_scenarios}",
            f"Toplam Sure: {suite_report.total_duration_ms}ms",
            f"Olusturulma: {suite_report.generated_at}",
            "",
        ]

        for report in suite_report.scenario_reports:
            scenario_text = self.format_report_text(report)
            lines.append(scenario_text)
            lines.append("")

        return "\n".join(lines)

    def format_report_json(self, report: TestReport) -> str:
        """Senaryo raporunu JSON formatinda olusturur.

        Args:
            report: Senaryo raporu.

        Returns:
            JSON string.
        """
        return report.model_dump_json(indent=2)

    def format_suite_report_json(self, suite_report: TestSuiteReport) -> str:
        """Suite raporunu JSON formatinda olusturur.

        Args:
            suite_report: Suite raporu.

        Returns:
            JSON string.
        """
        return suite_report.model_dump_json(indent=2)

    def save_report(
        self,
        report: TestReport | TestSuiteReport,
        filename: str,
        format_type: str = "json",
    ) -> Path | None:
        """Raporu dosyaya kaydeder.

        Args:
            report: Rapor (senaryo veya suite).
            filename: Dosya adi (uzanti olmadan).
            format_type: Format tipi ("json" veya "text").

        Returns:
            Kaydedilen dosyanin yolu veya None (report_dir tanimlanmamissa).
        """
        if self._report_dir is None:
            return None

        self._report_dir.mkdir(parents=True, exist_ok=True)

        if format_type == "json":
            if isinstance(report, TestSuiteReport):
                content = self.format_suite_report_json(report)
            else:
                content = self.format_report_json(report)
            file_path = self._report_dir / f"{filename}.json"
        else:
            if isinstance(report, TestSuiteReport):
                content = self.format_suite_report_text(report)
            else:
                content = self.format_report_text(report)
            file_path = self._report_dir / f"{filename}.txt"

        file_path.write_text(content, encoding="utf-8")
        return file_path

    async def upload_report(
        self,
        report: TestReport | TestSuiteReport,
        s3_key: str,
    ) -> str | None:
        """Raporu S3'e yukler.

        Args:
            report: Rapor (senaryo veya suite).
            s3_key: S3 object key.

        Returns:
            S3 URL veya None (s3_uploader tanimlanmamissa).
        """
        if self._s3_uploader is None:
            return None

        if isinstance(report, TestSuiteReport):
            content = self.format_suite_report_json(report)
        else:
            content = self.format_report_json(report)

        data = content.encode("utf-8")

        try:
            result = await self._s3_uploader.upload_bytes(
                data=data,
                key=s3_key,
                content_type="application/json",
            )
            await logger.ainfo(
                "Rapor S3'e yuklendi",
                s3_key=s3_key,
                url=result.url,
            )
            return result.url
        except Exception as exc:
            await logger.awarning(
                "Rapor S3 yukleme hatasi",
                s3_key=s3_key,
                error=str(exc),
            )
            return None

    def generate_summary(self, suite_report: TestSuiteReport) -> dict[str, object]:
        """Suite raporu icin ozet bilgi olusturur.

        Args:
            suite_report: Suite raporu.

        Returns:
            Ozet dictionary'si.
        """
        all_passed = suite_report.failed_scenarios == 0
        total_steps = sum(r.total_steps for r in suite_report.scenario_reports)
        passed_steps = sum(r.passed_steps for r in suite_report.scenario_reports)
        failed_steps = sum(r.failed_steps for r in suite_report.scenario_reports)

        failed_scenario_names = [
            r.scenario_name for r in suite_report.scenario_reports if not r.passed
        ]

        return {
            "suite_name": suite_report.suite_name,
            "overall_status": "PASSED" if all_passed else "FAILED",
            "total_scenarios": suite_report.total_scenarios,
            "passed_scenarios": suite_report.passed_scenarios,
            "failed_scenarios": suite_report.failed_scenarios,
            "total_steps": total_steps,
            "passed_steps": passed_steps,
            "failed_steps": failed_steps,
            "total_duration_ms": suite_report.total_duration_ms,
            "failed_scenario_names": failed_scenario_names,
        }
