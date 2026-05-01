"""Maestro test rapor olusturucu - JSON ve text formatlari.

Maestro suite sonuclarini okunabilir formatlarda raporlar.
Opsiyonel S3 upload destegi saglar.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from agent.testing.mobile.models import MaestroFlowResult, MaestroSuiteReport

if TYPE_CHECKING:
    from agent.upload.s3_uploader import S3Uploader

logger = structlog.get_logger()


class MaestroReporter:
    """Maestro test sonuc raporcusu.

    JSON ve text formatinda rapor uretir.
    S3'e rapor yukleme destegi saglar.

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

    def format_flow_text(self, result: MaestroFlowResult) -> str:
        """Flow sonucunu okunabilir text formatinda olusturur.

        Args:
            result: Flow sonucu.

        Returns:
            Formatlanmis text.
        """
        status = "PASSED" if result.success else "FAILED"
        lines: list[str] = [
            f"  Flow: {result.flow_name}",
            f"  Dosya: {result.flow_file}",
            f"  Platform: {result.platform}",
            f"  Durum: {status}",
            f"  Testler: {result.passed_tests}/{result.total_tests} basarili",
            f"  Sure: {result.duration_ms}ms",
        ]

        if result.timed_out:
            lines.append("  Zaman Asimi: EVET")

        if result.error:
            lines.append(f"  Hata: {result.error}")

        if result.screenshots:
            lines.append(f"  Screenshot sayisi: {len(result.screenshots)}")
            for ss in result.screenshots:
                if ss.url:
                    lines.append(f"    - {ss.url}")
                elif ss.path:
                    lines.append(f"    - (lokal) {ss.path}")

        return "\n".join(lines)

    def format_suite_text(self, report: MaestroSuiteReport) -> str:
        """Suite raporunu okunabilir text formatinda olusturur.

        Args:
            report: Suite raporu.

        Returns:
            Formatlanmis text.
        """
        overall = "PASSED" if report.all_passed else "FAILED"
        lines: list[str] = [
            f"{'=' * 60}",
            f"Maestro Test Raporu: {report.suite_name}",
            f"{'=' * 60}",
            f"Genel Durum: {overall}",
            f"Toplam Flow: {report.total_flows}",
            f"Basarili Flow: {report.passed_flows}",
            f"Basarisiz Flow: {report.failed_flows}",
            f"Toplam Test: {report.total_tests}",
            f"Basarili Test: {report.passed_tests}",
            f"Basarisiz Test: {report.failed_tests}",
            f"Toplam Sure: {report.total_duration_ms}ms",
            f"Olusturulma: {report.generated_at}",
            "",
            "Flow Detaylari:",
            f"{'-' * 40}",
        ]

        for flow_result in report.flow_results:
            flow_status = "PASS" if flow_result.success else "FAIL"
            lines.append(f"[{flow_status}] {flow_result.flow_name}")
            lines.append(self.format_flow_text(flow_result))
            lines.append("")

        lines.append(f"{'=' * 60}")
        return "\n".join(lines)

    def format_suite_json(self, report: MaestroSuiteReport) -> str:
        """Suite raporunu JSON formatinda olusturur.

        Args:
            report: Suite raporu.

        Returns:
            JSON string.
        """
        return report.model_dump_json(indent=2)

    def save_report(
        self,
        report: MaestroSuiteReport,
        filename: str,
        format_type: str = "json",
    ) -> Path | None:
        """Raporu dosyaya kaydeder.

        Args:
            report: Suite raporu.
            filename: Dosya adi (uzanti olmadan).
            format_type: Format tipi ("json" veya "text").

        Returns:
            Kaydedilen dosyanin yolu veya None.
        """
        if self._report_dir is None:
            return None

        self._report_dir.mkdir(parents=True, exist_ok=True)

        if format_type == "json":
            content = self.format_suite_json(report)
            file_path = self._report_dir / f"{filename}.json"
        else:
            content = self.format_suite_text(report)
            file_path = self._report_dir / f"{filename}.txt"

        file_path.write_text(content, encoding="utf-8")
        return file_path

    async def upload_report(
        self,
        report: MaestroSuiteReport,
        s3_key: str,
    ) -> str | None:
        """Raporu S3'e yukler.

        Args:
            report: Suite raporu.
            s3_key: S3 object key.

        Returns:
            S3 URL veya None.
        """
        if self._s3_uploader is None:
            return None

        content = self.format_suite_json(report)
        data = content.encode("utf-8")

        try:
            result = await self._s3_uploader.upload_bytes(
                data=data,
                key=s3_key,
                content_type="application/json",
            )
            await logger.ainfo(
                "Maestro raporu S3'e yuklendi",
                s3_key=s3_key,
                url=result.url,
            )
            return result.url
        except Exception as exc:
            await logger.awarning(
                "Maestro raporu S3 yukleme hatasi",
                s3_key=s3_key,
                error=str(exc),
            )
            return None

    def generate_summary(self, report: MaestroSuiteReport) -> dict[str, object]:
        """Suite raporu icin ozet bilgi olusturur.

        Args:
            report: Suite raporu.

        Returns:
            Ozet dictionary'si.
        """
        failed_flow_names = [r.flow_name for r in report.flow_results if not r.success]

        total_screenshots = sum(len(r.screenshots) for r in report.flow_results)

        return {
            "suite_name": report.suite_name,
            "overall_status": "PASSED" if report.all_passed else "FAILED",
            "total_flows": report.total_flows,
            "passed_flows": report.passed_flows,
            "failed_flows": report.failed_flows,
            "total_tests": report.total_tests,
            "passed_tests": report.passed_tests,
            "failed_tests": report.failed_tests,
            "total_duration_ms": report.total_duration_ms,
            "failed_flow_names": failed_flow_names,
            "total_screenshots": total_screenshots,
        }
