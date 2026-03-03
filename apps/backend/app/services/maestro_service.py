"""Maestro mobile test entegrasyon servisi.

Maestro flow tanimlama, calistirma, sonuc raporlama ve
screenshot rapor islemlerini yonetir. Agent tarafindaki
MaestroRunner ile WebSocket uzerinden haberlesir.
"""

from __future__ import annotations

import uuid

import structlog

from app.schemas.maestro import (
    FlowResult,
    FlowStepScreenshot,
    ListFlowsResponse,
    MaestroFlowDefinition,
    MaestroFlowStatus,
    MaestroRunStatus,
    MaestroTestReport,
    RunFlowResponse,
    RunSuiteResponse,
    ScreenshotResponse,
    SuiteResult,
    ValidateFlowResponse,
)

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


def _determine_flow_status(result: dict[str, object]) -> MaestroFlowStatus:
    """Runner sonucundan flow durumunu belirler.

    Args:
        result: MaestroRunner sonuc dictionary'si.

    Returns:
        Flow durumu.
    """
    if result.get("timed_out"):
        return MaestroFlowStatus.TIMEOUT

    if result.get("error") and not result.get("success"):
        return MaestroFlowStatus.ERROR

    if result.get("success"):
        failed = result.get("failed_tests", 0)
        if isinstance(failed, int) and failed > 0:
            return MaestroFlowStatus.FAILED
        return MaestroFlowStatus.PASSED

    return MaestroFlowStatus.FAILED


def _determine_suite_status(
    flow_results: list[FlowResult],
) -> MaestroRunStatus:
    """Flow sonuclarindan suite durumunu belirler.

    Args:
        flow_results: Flow sonuclari listesi.

    Returns:
        Suite durumu.
    """
    if not flow_results:
        return MaestroRunStatus.FAILED

    passed_count = sum(1 for r in flow_results if r.status == MaestroFlowStatus.PASSED)
    failed_count = len(flow_results) - passed_count

    if failed_count == 0:
        return MaestroRunStatus.COMPLETED
    if passed_count == 0:
        return MaestroRunStatus.FAILED
    return MaestroRunStatus.PARTIAL


def _extract_int(value: object, default: int = 0) -> int:
    """Degerden int cikarir, donusturemezse default doner.

    Args:
        value: Donusturulecek deger.
        default: Varsayilan deger.

    Returns:
        Integer deger.
    """
    if isinstance(value, int):
        return value
    if isinstance(value, (float, str)):
        try:
            return int(value)
        except (ValueError, TypeError):
            return default
    return default


def _build_flow_result(
    runner_result: dict[str, object],
    flow_file: str,
    platform: str,
) -> FlowResult:
    """Runner sonucundan FlowResult olusturur.

    Args:
        runner_result: MaestroRunner sonuc dictionary'si.
        flow_file: Flow dosya yolu.
        platform: Platform adi.

    Returns:
        FlowResult instance.
    """
    status = _determine_flow_status(runner_result)

    screenshots: list[str] = []
    raw_screenshots = runner_result.get("screenshots")
    if isinstance(raw_screenshots, list):
        screenshots = [str(s) for s in raw_screenshots if s]

    output_raw = runner_result.get("output")
    output = str(output_raw) if output_raw else None

    error_raw = runner_result.get("error")
    error = str(error_raw) if error_raw else None

    return FlowResult(
        flow_file=flow_file,
        platform=platform,
        status=status,
        total_tests=_extract_int(runner_result.get("total_tests")),
        passed_tests=_extract_int(runner_result.get("passed_tests")),
        failed_tests=_extract_int(runner_result.get("failed_tests")),
        duration_ms=_extract_int(runner_result.get("duration_ms")),
        error=error,
        screenshots=screenshots,
        output=output,
        timed_out=bool(runner_result.get("timed_out", False)),
    )


class MaestroService:
    """Maestro mobile test yonetim servisi.

    Flow tanimlama, calistirma, sonuc raporlama ve screenshot
    islemlerini yonetir. Agent'taki MaestroRunner'a tool dispatch
    yapar.
    """

    async def run_flow(
        self,
        *,
        runner_result: dict[str, object],
        flow_file: str,
        platform: str,
    ) -> RunFlowResponse:
        """Tek bir flow calistirma sonucunu isler.

        Args:
            runner_result: MaestroRunner.execute() sonucu.
            flow_file: Flow dosya yolu.
            platform: Hedef platform.

        Returns:
            RunFlowResponse.
        """
        result = _build_flow_result(runner_result, flow_file, platform)

        await logger.ainfo(
            "maestro_flow_completed",
            flow_file=flow_file,
            platform=platform,
            status=result.status,
            passed=result.passed_tests,
            failed=result.failed_tests,
            duration_ms=result.duration_ms,
        )

        return RunFlowResponse(
            success=result.status == MaestroFlowStatus.PASSED,
            result=result,
        )

    async def run_suite(
        self,
        *,
        suite_name: str,
        flows: list[MaestroFlowDefinition],
        runner_results: list[dict[str, object]],
        stop_on_failure: bool = False,  # noqa: ARG002
    ) -> RunSuiteResponse:
        """Suite calistirma sonuclarini isler.

        Args:
            suite_name: Suite adi.
            flows: Flow tanimlari.
            runner_results: Her flow icin runner sonuclari.
            stop_on_failure: Hata olunca durmus mu (loglama icin).

        Returns:
            RunSuiteResponse.
        """
        flow_results: list[FlowResult] = []
        all_screenshots: list[str] = []

        for flow_def, runner_result in zip(flows, runner_results, strict=False):
            result = _build_flow_result(
                runner_result,
                flow_def.flow_file,
                flow_def.platform,
            )
            flow_results.append(result)
            all_screenshots.extend(result.screenshots)

        total_duration_from_flows = sum(r.duration_ms for r in flow_results)

        status = _determine_suite_status(flow_results)
        total_tests = sum(r.total_tests for r in flow_results)
        passed_tests = sum(r.passed_tests for r in flow_results)
        failed_tests = sum(r.failed_tests for r in flow_results)
        passed_flows = sum(1 for r in flow_results if r.status == MaestroFlowStatus.PASSED)
        failed_flows = len(flow_results) - passed_flows

        suite_result = SuiteResult(
            suite_name=suite_name,
            status=status,
            total_flows=len(flow_results),
            passed_flows=passed_flows,
            failed_flows=failed_flows,
            total_tests=total_tests,
            passed_tests=passed_tests,
            failed_tests=failed_tests,
            duration_ms=total_duration_from_flows,
            flow_results=flow_results,
            screenshots=all_screenshots,
        )

        await logger.ainfo(
            "maestro_suite_completed",
            suite_name=suite_name,
            status=status,
            total_flows=len(flow_results),
            passed_flows=passed_flows,
            failed_flows=failed_flows,
            duration_ms=total_duration_from_flows,
        )

        return RunSuiteResponse(
            success=status == MaestroRunStatus.COMPLETED,
            result=suite_result,
        )

    async def process_validate_result(
        self,
        *,
        runner_result: dict[str, object],
        flow_file: str,
    ) -> ValidateFlowResponse:
        """Flow dogrulama sonucunu isler.

        Args:
            runner_result: MaestroRunner validate_flow sonucu.
            flow_file: Dogrulanan flow dosya yolu.

        Returns:
            ValidateFlowResponse.
        """
        valid = bool(runner_result.get("valid", False))
        error_raw = runner_result.get("error")
        error = str(error_raw) if error_raw else None

        return ValidateFlowResponse(
            valid=valid,
            flow_file=flow_file,
            file_size_bytes=_extract_int(runner_result.get("file_size_bytes")),
            has_known_commands=bool(runner_result.get("has_known_commands", False)),
            error=error,
        )

    async def process_screenshot_result(
        self,
        *,
        runner_result: dict[str, object],
        platform: str,
    ) -> ScreenshotResponse:
        """Screenshot alma sonucunu isler.

        Args:
            runner_result: MaestroRunner take_screenshot sonucu.
            platform: Platform adi.

        Returns:
            ScreenshotResponse.
        """
        success = bool(runner_result.get("success", False))

        screenshot_url_raw = runner_result.get("screenshot_url")
        screenshot_url = str(screenshot_url_raw) if screenshot_url_raw else None

        screenshot_path_raw = runner_result.get("screenshot_path")
        screenshot_path = str(screenshot_path_raw) if screenshot_path_raw else None

        error_raw = runner_result.get("error")
        error = str(error_raw) if error_raw else None

        return ScreenshotResponse(
            success=success,
            screenshot_url=screenshot_url,
            screenshot_path=screenshot_path,
            platform=platform,
            error=error,
        )

    async def process_list_flows_result(
        self,
        *,
        runner_result: dict[str, object],
    ) -> ListFlowsResponse:
        """Flow listesi sonucunu isler.

        Args:
            runner_result: MaestroRunner list_flows sonucu.

        Returns:
            ListFlowsResponse.
        """
        from app.schemas.maestro import FlowFileInfo

        success = bool(runner_result.get("success", False))
        flows_dir_raw = runner_result.get("flows_dir", "")
        flows_dir = str(flows_dir_raw)
        flow_count = _extract_int(runner_result.get("flow_count"))

        error_raw = runner_result.get("error")
        error = str(error_raw) if error_raw else None

        flows: list[FlowFileInfo] = []
        raw_flows = runner_result.get("flows")
        if isinstance(raw_flows, list):
            for item in raw_flows:
                if isinstance(item, dict):
                    flows.append(
                        FlowFileInfo(
                            name=str(item.get("name", "")),
                            path=str(item.get("path", "")),
                            size_bytes=_extract_int(item.get("size_bytes")),
                        ),
                    )

        return ListFlowsResponse(
            success=success,
            flows_dir=flows_dir,
            flow_count=flow_count,
            flows=flows,
            error=error,
        )

    async def generate_test_report(
        self,
        *,
        suite_response: RunSuiteResponse,
    ) -> MaestroTestReport:
        """Suite sonucundan CI raporu olusturur.

        Args:
            suite_response: Suite calistirma yaniti.

        Returns:
            MaestroTestReport (CI entegrasyonu icin).
        """
        suite = suite_response.result
        run_id = str(uuid.uuid4())

        # Screenshot bilgilerini duzenle
        screenshots: list[FlowStepScreenshot] = []
        for flow_result in suite.flow_results:
            for idx, url in enumerate(flow_result.screenshots):
                screenshots.append(
                    FlowStepScreenshot(
                        step_name=f"{flow_result.flow_file}:step-{idx + 1}",
                        screenshot_url=url,
                    ),
                )

        report = MaestroTestReport(
            run_id=run_id,
            suite_name=suite.suite_name,
            status=suite.status,
            total_flows=suite.total_flows,
            passed_flows=suite.passed_flows,
            failed_flows=suite.failed_flows,
            total_tests=suite.total_tests,
            passed_tests=suite.passed_tests,
            failed_tests=suite.failed_tests,
            duration_ms=suite.duration_ms,
            flow_results=suite.flow_results,
            screenshots=screenshots,
        )

        await logger.ainfo(
            "maestro_report_generated",
            run_id=run_id,
            suite_name=suite.suite_name,
            status=suite.status,
            total_flows=suite.total_flows,
        )

        return report
