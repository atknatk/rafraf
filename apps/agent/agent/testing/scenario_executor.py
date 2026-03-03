"""Senaryo calistiricisi - test senaryolarini PlaywrightRunner uzerinden yurutur.

Her senaryo adimini sirasiyla calistirir, assertion dogrulama yapar,
visual regression kontrol eder ve sonuclari toplar.
"""

from __future__ import annotations

import base64
import time
from typing import TYPE_CHECKING

import structlog

from agent.testing.models import (
    AssertionResult,
    AssertionType,
    ScenarioStep,
    StepType,
    TestAssertion,
    TestReport,
    TestScenario,
    TestStepResult,
    TestSuiteReport,
)
from agent.testing.visual_regression import VisualRegressionChecker

if TYPE_CHECKING:
    from agent.runners.playwright_runner import PlaywrightRunner

logger = structlog.get_logger()


def _resolve_url(step_url: str, base_url: str) -> str:
    """Adim URL'ini base URL ile birlestirir.

    Args:
        step_url: Adim URL'i (tam veya goreceli).
        base_url: Senaryo temel URL'i.

    Returns:
        Tam URL.
    """
    if step_url.startswith(("http://", "https://")):
        return step_url

    if base_url:
        base = base_url.rstrip("/")
        relative = step_url.lstrip("/")
        return f"{base}/{relative}"

    return step_url


def _map_step_to_action(step_type: StepType) -> str:
    """StepType'i PlaywrightRunner action string'ine donusturur.

    Args:
        step_type: Test adim tipi.

    Returns:
        Runner action string.
    """
    mapping: dict[StepType, str] = {
        StepType.PAGE_LOAD: "check_page_load",
        StepType.CHECK_ELEMENT: "check_element",
        StepType.FILL_FORM: "fill_form",
        StepType.TAKE_SCREENSHOT: "take_screenshot",
        StepType.WAIT_FOR_RESPONSE: "wait_for_response",
        StepType.VISUAL_REGRESSION: "take_screenshot",
    }
    return mapping[step_type]


def _evaluate_assertion(
    assertion_type: AssertionType,
    expected: str | int | float | bool,
    runner_result: dict[str, object],
) -> AssertionResult:
    """Tek bir assertion'i degerlendirir.

    Args:
        assertion_type: Assertion tipi.
        expected: Beklenen deger.
        runner_result: PlaywrightRunner sonucu.

    Returns:
        Degerlendirme sonucu.
    """
    actual: str | int | float | bool | None = None
    passed = False
    message = ""

    if assertion_type == AssertionType.STATUS_CODE:
        raw_status = runner_result.get("status_code")
        actual = int(str(raw_status)) if raw_status is not None else None
        if actual is not None:
            passed = actual == int(expected)
        message = f"Status code: beklenen={expected}, gerceklesen={actual}"

    elif assertion_type == AssertionType.TITLE_CONTAINS:
        actual = str(runner_result.get("page_title", ""))
        passed = str(expected).lower() in actual.lower()
        message = f"Title contains: beklenen='{expected}', baslik='{actual}'"

    elif assertion_type == AssertionType.TITLE_EQUALS:
        actual = str(runner_result.get("page_title", ""))
        passed = actual == str(expected)
        message = f"Title equals: beklenen='{expected}', gerceklesen='{actual}'"

    elif assertion_type == AssertionType.ELEMENT_EXISTS:
        raw_found = runner_result.get("element_found")
        if raw_found is None:
            raw_found = runner_result.get("success", False)
        actual = bool(raw_found)
        passed = actual == bool(expected)
        message = f"Element exists: beklenen={expected}, gerceklesen={actual}"

    elif assertion_type == AssertionType.ELEMENT_VISIBLE:
        raw_visible = runner_result.get("element_visible")
        actual = bool(raw_visible) if raw_visible is not None else False
        passed = actual == bool(expected)
        message = f"Element visible: beklenen={expected}, gerceklesen={actual}"

    elif assertion_type == AssertionType.ELEMENT_TEXT_CONTAINS:
        raw_text = runner_result.get("element_text", "")
        actual = str(raw_text) if raw_text is not None else ""
        passed = str(expected).lower() in actual.lower()
        message = f"Element text contains: beklenen='{expected}', gerceklesen='{actual}'"

    elif assertion_type == AssertionType.ELEMENT_TEXT_EQUALS:
        raw_text = runner_result.get("element_text", "")
        actual = str(raw_text) if raw_text is not None else ""
        passed = actual == str(expected)
        message = f"Element text equals: beklenen='{expected}', gerceklesen='{actual}'"

    elif assertion_type == AssertionType.LOAD_TIME_UNDER:
        raw_time = runner_result.get("load_time_ms", 0)
        actual = int(str(raw_time)) if raw_time is not None else 0
        passed = actual <= int(expected)
        message = f"Load time: beklenen<={expected}ms, gerceklesen={actual}ms"

    elif assertion_type == AssertionType.RESPONSE_STATUS:
        raw_resp_status = runner_result.get("response_status")
        actual = int(str(raw_resp_status)) if raw_resp_status is not None else None
        if actual is not None:
            passed = actual == int(expected)
        message = f"Response status: beklenen={expected}, gerceklesen={actual}"

    elif assertion_type == AssertionType.SCREENSHOT_MATCH:
        # Visual regression assertion'i ayri islenecek
        passed = bool(runner_result.get("visual_match", False))
        raw_diff = runner_result.get("diff_ratio", 1.0)
        actual = float(str(raw_diff))
        message = str(runner_result.get("visual_message", ""))

    return AssertionResult(
        assertion_type=assertion_type,
        passed=passed,
        expected=expected,
        actual=actual,
        message=message,
    )


class ScenarioExecutor:
    """Test senaryolarini PlaywrightRunner ile calistiran executor.

    Args:
        runner: PlaywrightRunner instance.
        visual_checker: Visual regression checker (opsiyonel).
    """

    def __init__(
        self,
        runner: PlaywrightRunner,
        visual_checker: VisualRegressionChecker | None = None,
    ) -> None:
        self._runner = runner
        self._visual_checker = visual_checker

    async def execute_scenario(self, scenario: TestScenario) -> TestReport:
        """Tek bir test senaryosunu calistirir.

        Senaryodaki adimlari sirasiyla yurutur. Bir adim basarisiz olursa
        sonraki adimlar calistirilmaya devam eder (fail-continue stratejisi).

        Args:
            scenario: Calistirilacak test senaryosu.

        Returns:
            Senaryo raporu.
        """
        started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        overall_start = time.monotonic()
        step_results: list[TestStepResult] = []
        scenario_error: str | None = None

        await logger.ainfo(
            "Senaryo baslatiliyor",
            scenario=scenario.name,
            step_count=len(scenario.steps),
        )

        for step in scenario.steps:
            try:
                step_result = await self._execute_step(step, scenario.base_url)
                step_results.append(step_result)
            except Exception as exc:
                error_msg = str(exc)
                step_results.append(
                    TestStepResult(
                        step_name=step.name,
                        step_type=step.type,
                        passed=False,
                        error=f"Beklenmeyen hata: {error_msg}",
                    ),
                )
                await logger.awarning(
                    "Adim calistirma hatasi",
                    scenario=scenario.name,
                    step=step.name,
                    error=error_msg,
                )

        overall_duration = int((time.monotonic() - overall_start) * 1000)
        finished_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        passed_count = sum(1 for r in step_results if r.passed)
        failed_count = sum(1 for r in step_results if not r.passed)
        all_passed = failed_count == 0 and len(step_results) > 0

        await logger.ainfo(
            "Senaryo tamamlandi",
            scenario=scenario.name,
            passed=all_passed,
            passed_steps=passed_count,
            failed_steps=failed_count,
            duration_ms=overall_duration,
        )

        return TestReport(
            scenario_name=scenario.name,
            passed=all_passed,
            total_steps=len(step_results),
            passed_steps=passed_count,
            failed_steps=failed_count,
            duration_ms=overall_duration,
            step_results=step_results,
            started_at=started_at,
            finished_at=finished_at,
            error=scenario_error,
        )

    async def execute_suite(
        self,
        scenarios: list[TestScenario],
        suite_name: str = "default",
    ) -> TestSuiteReport:
        """Birden fazla senaryoyu calistirir ve suite raporu olusturur.

        Args:
            scenarios: Calistirilacak senaryolar.
            suite_name: Suite adi (raporlama icin).

        Returns:
            Suite raporu.
        """
        suite_start = time.monotonic()
        reports: list[TestReport] = []

        for scenario in scenarios:
            report = await self.execute_scenario(scenario)
            reports.append(report)

        total_duration = int((time.monotonic() - suite_start) * 1000)
        passed_count = sum(1 for r in reports if r.passed)
        failed_count = sum(1 for r in reports if not r.passed)

        return TestSuiteReport(
            suite_name=suite_name,
            total_scenarios=len(reports),
            passed_scenarios=passed_count,
            failed_scenarios=failed_count,
            total_duration_ms=total_duration,
            scenario_reports=reports,
        )

    async def _execute_step(
        self,
        step: ScenarioStep,
        base_url: str,
    ) -> TestStepResult:
        """Tek bir adimi calistirir ve assertion'lari kontrol eder.

        Args:
            step: Calistirilacak adim.
            base_url: Senaryo base URL'i.

        Returns:
            Adim sonucu.
        """
        resolved_url = _resolve_url(step.url, base_url)
        action = _map_step_to_action(step.type)
        params: dict[str, object] = {"url": resolved_url, **step.params}

        step_start = time.monotonic()

        # Runner'i calistir
        runner_result = await self._runner.execute(action, params)
        duration_ms = int((time.monotonic() - step_start) * 1000)

        # Runner basarisizsa direkt fail
        if not runner_result.get("success", False):
            return TestStepResult(
                step_name=step.name,
                step_type=step.type,
                passed=False,
                duration_ms=duration_ms,
                runner_result=runner_result,
                error=str(runner_result.get("error", "Bilinmeyen hata")),
            )

        # Visual regression kontrolu
        if step.type == StepType.VISUAL_REGRESSION:
            runner_result = self._handle_visual_regression(
                runner_result,
                step,
            )

        # Assertion'lari degerlendir
        assertion_results = self._evaluate_assertions(step.assertions, runner_result)
        all_assertions_passed = all(ar.passed for ar in assertion_results)
        step_passed = all_assertions_passed

        # Screenshot bilgisi
        screenshot_url = runner_result.get("screenshot_url")
        screenshot_base64 = runner_result.get("screenshot_base64")

        return TestStepResult(
            step_name=step.name,
            step_type=step.type,
            passed=step_passed,
            duration_ms=duration_ms,
            runner_result=runner_result,
            assertion_results=assertion_results,
            screenshot_url=str(screenshot_url) if screenshot_url else None,
            screenshot_base64=str(screenshot_base64) if screenshot_base64 else None,
        )

    def _handle_visual_regression(
        self,
        runner_result: dict[str, object],
        step: ScenarioStep,
    ) -> dict[str, object]:
        """Visual regression kontrolu yapar.

        Args:
            runner_result: Runner sonucu (screenshot verisi icermeli).
            step: Test adimi (tolerance bilgisi icin).

        Returns:
            Visual regression bilgileri eklenmis runner sonucu.
        """
        if self._visual_checker is None:
            return {
                **runner_result,
                "visual_match": False,
                "diff_ratio": 1.0,
                "visual_message": "VisualRegressionChecker tanimlanmamis.",
            }

        # Screenshot verisini al
        screenshot_data = self._get_screenshot_bytes(runner_result)
        if screenshot_data is None:
            return {
                **runner_result,
                "visual_match": False,
                "diff_ratio": 1.0,
                "visual_message": "Screenshot verisi bulunamadi.",
            }

        # Baseline adi olustur (step params'tan veya step name'den)
        baseline_name = str(step.params.get("baseline_name", f"{step.name}.png"))
        if not baseline_name.endswith(".png"):
            baseline_name = f"{baseline_name}.png"

        # Tolerans degerini assertions'dan al
        tolerance = 0.0
        for assertion in step.assertions:
            if assertion.type == AssertionType.SCREENSHOT_MATCH:
                tolerance = assertion.tolerance
                break

        # Karsilastir
        comparison = self._visual_checker.compare(
            screenshot_data=screenshot_data,
            baseline_name=baseline_name,
            tolerance=tolerance,
        )

        return {
            **runner_result,
            "visual_match": comparison.matched,
            "diff_ratio": comparison.diff_ratio,
            "visual_message": comparison.message,
        }

    def _get_screenshot_bytes(
        self,
        runner_result: dict[str, object],
    ) -> bytes | None:
        """Runner sonucundan screenshot byte verisini cikarir.

        Args:
            runner_result: Runner sonucu.

        Returns:
            Screenshot byte verisi veya None.
        """
        base64_data = runner_result.get("screenshot_base64")
        if isinstance(base64_data, str) and base64_data:
            try:
                return base64.b64decode(base64_data)
            except Exception:
                return None
        return None

    def _evaluate_assertions(
        self,
        assertions: list[TestAssertion],
        runner_result: dict[str, object],
    ) -> list[AssertionResult]:
        """Assertion listesini degerlendirir.

        Args:
            assertions: Assertion tanimlari.
            runner_result: Runner sonucu.

        Returns:
            Degerlendirme sonuclari.
        """
        results: list[AssertionResult] = []

        for assertion in assertions:
            result = _evaluate_assertion(
                assertion.type,
                assertion.expected,
                runner_result,
            )
            results.append(result)

        return results
