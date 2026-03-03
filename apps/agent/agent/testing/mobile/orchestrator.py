"""Maestro test orkestratoru - MaestroRunner uzerinden test akislarini yurutur.

Suite icerisindeki flow'lari sirasiyla calistirir,
sonuclari toplar ve raporlar.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import structlog

from agent.testing.mobile.models import (
    MaestroFlowConfig,
    MaestroFlowResult,
    MaestroScreenshotInfo,
    MaestroSuiteConfig,
    MaestroSuiteReport,
)

if TYPE_CHECKING:
    from agent.runners.maestro_runner import MaestroRunner

logger = structlog.get_logger()


def _extract_int(value: object, default: int = 0) -> int:
    """Degerden int cikarir.

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
    config: MaestroFlowConfig,
    runner_result: dict[str, object],
    duration_ms: int,
) -> MaestroFlowResult:
    """Runner sonucundan MaestroFlowResult olusturur.

    Args:
        config: Flow konfigurasyonu.
        runner_result: MaestroRunner.execute() sonucu.
        duration_ms: Calisma suresi.

    Returns:
        MaestroFlowResult instance.
    """
    success = bool(runner_result.get("success", False))
    timed_out = bool(runner_result.get("timed_out", False))

    # Screenshot bilgilerini topla
    screenshots: list[MaestroScreenshotInfo] = []
    raw_screenshots = runner_result.get("screenshots")
    if isinstance(raw_screenshots, list):
        for url in raw_screenshots:
            if url:
                screenshots.append(
                    MaestroScreenshotInfo(
                        flow_name=config.name,
                        url=str(url),
                    ),
                )

    # Lokal screenshot path
    screenshot_path_raw = runner_result.get("screenshot_path")
    if screenshot_path_raw and not screenshots:
        screenshots.append(
            MaestroScreenshotInfo(
                flow_name=config.name,
                path=str(screenshot_path_raw),
            ),
        )

    output_raw = runner_result.get("output")
    raw_output = str(output_raw) if output_raw else None

    error_raw = runner_result.get("error")
    error = str(error_raw) if error_raw else None

    return MaestroFlowResult(
        flow_name=config.name,
        flow_file=config.flow_file,
        platform=config.platform,
        success=success,
        total_tests=_extract_int(runner_result.get("total_tests")),
        passed_tests=_extract_int(runner_result.get("passed_tests")),
        failed_tests=_extract_int(runner_result.get("failed_tests")),
        duration_ms=duration_ms,
        error=error,
        timed_out=timed_out,
        screenshots=screenshots,
        raw_output=raw_output,
    )


class MaestroTestOrchestrator:
    """Maestro test akislarini yoneten orkestrator.

    MaestroRunner instance'i alir ve flow konfigurasyonlarini
    sirasiyla calistirir. Suite bazli veya tekil flow calistirma
    destekler.

    Args:
        runner: MaestroRunner instance.
    """

    def __init__(self, runner: MaestroRunner) -> None:
        self._runner = runner

    async def run_flow(self, config: MaestroFlowConfig) -> MaestroFlowResult:
        """Tek bir flow'u calistirir.

        Args:
            config: Flow konfigurasyonu.

        Returns:
            Flow sonucu.
        """
        await logger.ainfo(
            "Maestro flow baslatiliyor",
            flow_name=config.name,
            flow_file=config.flow_file,
            platform=config.platform,
        )

        params: dict[str, object] = {
            "flow_file": config.flow_file,
            "platform": config.platform.value,
            "timeout": config.timeout,
        }
        if config.cwd is not None:
            params["cwd"] = config.cwd
        if config.project_slug is not None:
            params["project_slug"] = config.project_slug

        start_time = time.monotonic()

        try:
            runner_result = await self._runner.execute("run_flow", params)
        except Exception as exc:
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            await logger.aerror(
                "Maestro flow calistirma hatasi",
                flow_name=config.name,
                error=str(exc),
            )
            return MaestroFlowResult(
                flow_name=config.name,
                flow_file=config.flow_file,
                platform=config.platform,
                success=False,
                duration_ms=elapsed_ms,
                error=str(exc),
            )

        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        result = _build_flow_result(config, runner_result, elapsed_ms)

        await logger.ainfo(
            "Maestro flow tamamlandi",
            flow_name=config.name,
            success=result.success,
            passed_tests=result.passed_tests,
            failed_tests=result.failed_tests,
            duration_ms=elapsed_ms,
        )

        return result

    async def run_suite(self, suite_config: MaestroSuiteConfig) -> MaestroSuiteReport:
        """Suite icerisindeki tum flow'lari sirasiyla calistirir.

        Args:
            suite_config: Suite konfigurasyonu.

        Returns:
            Suite raporu.
        """
        await logger.ainfo(
            "Maestro suite baslatiliyor",
            suite_name=suite_config.suite_name,
            flow_count=len(suite_config.flows),
            stop_on_failure=suite_config.stop_on_failure,
        )

        suite_start = time.monotonic()
        flow_results: list[MaestroFlowResult] = []

        for flow_config in suite_config.flows:
            result = await self.run_flow(flow_config)
            flow_results.append(result)

            # Stop on failure kontrolu
            if suite_config.stop_on_failure and not result.success:
                await logger.awarning(
                    "Suite durduruluyor (stop_on_failure)",
                    suite_name=suite_config.suite_name,
                    failed_flow=flow_config.name,
                )
                break

        total_duration = int((time.monotonic() - suite_start) * 1000)
        passed_flows = sum(1 for r in flow_results if r.success)
        failed_flows = len(flow_results) - passed_flows
        total_tests = sum(r.total_tests for r in flow_results)
        passed_tests = sum(r.passed_tests for r in flow_results)
        failed_tests = sum(r.failed_tests for r in flow_results)
        all_passed = failed_flows == 0 and len(flow_results) > 0

        report = MaestroSuiteReport(
            suite_name=suite_config.suite_name,
            total_flows=len(flow_results),
            passed_flows=passed_flows,
            failed_flows=failed_flows,
            total_tests=total_tests,
            passed_tests=passed_tests,
            failed_tests=failed_tests,
            total_duration_ms=total_duration,
            flow_results=flow_results,
            all_passed=all_passed,
        )

        await logger.ainfo(
            "Maestro suite tamamlandi",
            suite_name=suite_config.suite_name,
            all_passed=all_passed,
            passed_flows=passed_flows,
            failed_flows=failed_flows,
            total_duration_ms=total_duration,
        )

        return report
