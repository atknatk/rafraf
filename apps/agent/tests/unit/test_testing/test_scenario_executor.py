"""Unit tests for agent.testing.scenario_executor."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from agent.testing.models import (
    AssertionType,
    ScenarioStep,
    StepType,
    TestAssertion,
    TestScenario,
)
from agent.testing.scenario_executor import (
    ScenarioExecutor,
    _evaluate_assertion,
    _map_step_to_action,
    _resolve_url,
)
from agent.testing.visual_regression import VisualRegressionChecker

# --- Fixtures ---


@pytest.fixture
def mock_runner() -> AsyncMock:
    """Mock PlaywrightRunner olusturur."""
    runner = AsyncMock()
    runner.execute = AsyncMock(
        return_value={
            "success": True,
            "page_title": "Test Page",
            "status_code": 200,
            "load_time_ms": 150,
        },
    )
    return runner


@pytest.fixture
def executor(mock_runner: AsyncMock) -> ScenarioExecutor:
    """ScenarioExecutor olusturur."""
    return ScenarioExecutor(runner=mock_runner)


@pytest.fixture
def visual_checker(tmp_path: Path) -> VisualRegressionChecker:
    """VisualRegressionChecker olusturur."""
    baseline_dir = tmp_path / "baselines"
    baseline_dir.mkdir()
    return VisualRegressionChecker(baseline_dir=baseline_dir)


# --- _resolve_url Tests ---


class TestResolveUrl:
    """_resolve_url fonksiyon testleri."""

    def test_absolute_url_unchanged(self) -> None:
        """Mutlak URL degismez."""
        assert _resolve_url("https://example.com", "https://base.com") == "https://example.com"
        assert _resolve_url("http://example.com", "https://base.com") == "http://example.com"

    def test_relative_url_combined(self) -> None:
        """Goreceli URL base ile birlesir."""
        assert _resolve_url("/page", "https://example.com") == "https://example.com/page"
        assert _resolve_url("page", "https://example.com") == "https://example.com/page"

    def test_trailing_leading_slashes(self) -> None:
        """Fazla slash'lar temizlenir."""
        result = _resolve_url("/page", "https://example.com/")
        assert result == "https://example.com/page"

    def test_no_base_url(self) -> None:
        """Base URL yoksa relative URL degismez."""
        assert _resolve_url("/page", "") == "/page"


# --- _map_step_to_action Tests ---


class TestMapStepToAction:
    """_map_step_to_action fonksiyon testleri."""

    def test_all_mappings(self) -> None:
        """Tum StepType degerleri action'a eslesir."""
        assert _map_step_to_action(StepType.PAGE_LOAD) == "check_page_load"
        assert _map_step_to_action(StepType.CHECK_ELEMENT) == "check_element"
        assert _map_step_to_action(StepType.FILL_FORM) == "fill_form"
        assert _map_step_to_action(StepType.TAKE_SCREENSHOT) == "take_screenshot"
        assert _map_step_to_action(StepType.WAIT_FOR_RESPONSE) == "wait_for_response"
        assert _map_step_to_action(StepType.VISUAL_REGRESSION) == "take_screenshot"


# --- _evaluate_assertion Tests ---


class TestEvaluateAssertion:
    """_evaluate_assertion fonksiyon testleri."""

    def test_status_code_pass(self) -> None:
        """Status code assertion basarili."""
        result = _evaluate_assertion(
            AssertionType.STATUS_CODE,
            200,
            {"status_code": 200},
        )
        assert result.passed is True
        assert result.actual == 200

    def test_status_code_fail(self) -> None:
        """Status code assertion basarisiz."""
        result = _evaluate_assertion(
            AssertionType.STATUS_CODE,
            200,
            {"status_code": 404},
        )
        assert result.passed is False

    def test_status_code_none(self) -> None:
        """Status code yoksa basarisiz."""
        result = _evaluate_assertion(
            AssertionType.STATUS_CODE,
            200,
            {},
        )
        assert result.passed is False
        assert result.actual is None

    def test_title_contains_pass(self) -> None:
        """Title contains assertion basarili."""
        result = _evaluate_assertion(
            AssertionType.TITLE_CONTAINS,
            "Example",
            {"page_title": "Example Domain"},
        )
        assert result.passed is True

    def test_title_contains_case_insensitive(self) -> None:
        """Title contains buyuk/kucuk harf duyarsiz."""
        result = _evaluate_assertion(
            AssertionType.TITLE_CONTAINS,
            "example",
            {"page_title": "EXAMPLE Domain"},
        )
        assert result.passed is True

    def test_title_contains_fail(self) -> None:
        """Title contains basarisiz."""
        result = _evaluate_assertion(
            AssertionType.TITLE_CONTAINS,
            "NotHere",
            {"page_title": "Example Domain"},
        )
        assert result.passed is False

    def test_title_equals_pass(self) -> None:
        """Title equals assertion basarili."""
        result = _evaluate_assertion(
            AssertionType.TITLE_EQUALS,
            "Example Domain",
            {"page_title": "Example Domain"},
        )
        assert result.passed is True

    def test_title_equals_fail(self) -> None:
        """Title equals assertion basarisiz."""
        result = _evaluate_assertion(
            AssertionType.TITLE_EQUALS,
            "Other",
            {"page_title": "Example Domain"},
        )
        assert result.passed is False

    def test_element_exists_pass(self) -> None:
        """Element exists assertion basarili."""
        result = _evaluate_assertion(
            AssertionType.ELEMENT_EXISTS,
            True,
            {"element_found": True},
        )
        assert result.passed is True

    def test_element_exists_false(self) -> None:
        """Element bulunamadiginda False bekleniyor."""
        result = _evaluate_assertion(
            AssertionType.ELEMENT_EXISTS,
            False,
            {"element_found": False},
        )
        assert result.passed is True

    def test_element_visible_pass(self) -> None:
        """Element visible assertion basarili."""
        result = _evaluate_assertion(
            AssertionType.ELEMENT_VISIBLE,
            True,
            {"element_visible": True},
        )
        assert result.passed is True

    def test_element_text_contains_pass(self) -> None:
        """Element text contains assertion basarili."""
        result = _evaluate_assertion(
            AssertionType.ELEMENT_TEXT_CONTAINS,
            "hello",
            {"element_text": "Say hello world"},
        )
        assert result.passed is True

    def test_element_text_equals_pass(self) -> None:
        """Element text equals assertion basarili."""
        result = _evaluate_assertion(
            AssertionType.ELEMENT_TEXT_EQUALS,
            "Hello",
            {"element_text": "Hello"},
        )
        assert result.passed is True

    def test_load_time_under_pass(self) -> None:
        """Load time under assertion basarili."""
        result = _evaluate_assertion(
            AssertionType.LOAD_TIME_UNDER,
            1000,
            {"load_time_ms": 500},
        )
        assert result.passed is True

    def test_load_time_under_fail(self) -> None:
        """Load time asildiginda basarisiz."""
        result = _evaluate_assertion(
            AssertionType.LOAD_TIME_UNDER,
            100,
            {"load_time_ms": 500},
        )
        assert result.passed is False

    def test_response_status_pass(self) -> None:
        """Response status assertion basarili."""
        result = _evaluate_assertion(
            AssertionType.RESPONSE_STATUS,
            200,
            {"response_status": 200},
        )
        assert result.passed is True

    def test_response_status_none(self) -> None:
        """Response status yoksa basarisiz."""
        result = _evaluate_assertion(
            AssertionType.RESPONSE_STATUS,
            200,
            {},
        )
        assert result.passed is False

    def test_screenshot_match_pass(self) -> None:
        """Screenshot match assertion basarili."""
        result = _evaluate_assertion(
            AssertionType.SCREENSHOT_MATCH,
            True,
            {"visual_match": True, "diff_ratio": 0.0, "visual_message": "OK"},
        )
        assert result.passed is True

    def test_screenshot_match_fail(self) -> None:
        """Screenshot match assertion basarisiz."""
        result = _evaluate_assertion(
            AssertionType.SCREENSHOT_MATCH,
            True,
            {"visual_match": False, "diff_ratio": 0.5, "visual_message": "Different"},
        )
        assert result.passed is False


# --- ScenarioExecutor.execute_scenario Tests ---


class TestExecuteScenario:
    """ScenarioExecutor.execute_scenario() testleri."""

    async def test_empty_scenario(self, executor: ScenarioExecutor) -> None:
        """Bos senaryo passed=False (no steps)."""
        scenario = TestScenario(name="Empty")
        report = await executor.execute_scenario(scenario)
        # Adim yoksa all_passed = False (len(step_results) == 0)
        assert report.passed is False
        assert report.total_steps == 0

    async def test_single_step_pass(
        self,
        executor: ScenarioExecutor,
        mock_runner: AsyncMock,
    ) -> None:
        """Tek adimli senaryo basarili."""
        scenario = TestScenario(
            name="Single Step",
            steps=[
                ScenarioStep(
                    name="Load Page",
                    type=StepType.PAGE_LOAD,
                    url="https://example.com",
                ),
            ],
        )

        report = await executor.execute_scenario(scenario)
        assert report.passed is True
        assert report.total_steps == 1
        assert report.passed_steps == 1
        assert report.failed_steps == 0
        mock_runner.execute.assert_called_once()

    async def test_single_step_fail(
        self,
        executor: ScenarioExecutor,
        mock_runner: AsyncMock,
    ) -> None:
        """Basarisiz adim senaryo fail eder."""
        mock_runner.execute.return_value = {
            "success": False,
            "error": "Connection failed",
        }

        scenario = TestScenario(
            name="Fail Step",
            steps=[
                ScenarioStep(
                    name="Load Page",
                    type=StepType.PAGE_LOAD,
                    url="https://bad.example.com",
                ),
            ],
        )

        report = await executor.execute_scenario(scenario)
        assert report.passed is False
        assert report.failed_steps == 1

    async def test_multiple_steps_continue_on_failure(
        self,
        executor: ScenarioExecutor,
        mock_runner: AsyncMock,
    ) -> None:
        """Bir adim basarisiz olsa bile sonrakiler calisir."""
        call_count = 0

        async def side_effect(_action: str, _params: dict[str, object]) -> dict[str, object]:
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                return {"success": False, "error": "fail"}
            return {"success": True, "page_title": "OK", "status_code": 200}

        mock_runner.execute.side_effect = side_effect

        scenario = TestScenario(
            name="Multi Step",
            steps=[
                ScenarioStep(name="Step 1", type=StepType.PAGE_LOAD, url="https://example.com"),
                ScenarioStep(name="Step 2", type=StepType.PAGE_LOAD, url="https://example.com"),
                ScenarioStep(name="Step 3", type=StepType.PAGE_LOAD, url="https://example.com"),
            ],
        )

        report = await executor.execute_scenario(scenario)
        assert report.total_steps == 3
        assert report.passed_steps == 2
        assert report.failed_steps == 1
        assert report.passed is False

    async def test_assertions_evaluated(
        self,
        executor: ScenarioExecutor,
    ) -> None:
        """Assertion'lar degerlendirilir."""
        scenario = TestScenario(
            name="Assertion Test",
            steps=[
                ScenarioStep(
                    name="Load",
                    type=StepType.PAGE_LOAD,
                    url="https://example.com",
                    assertions=[
                        TestAssertion(type=AssertionType.STATUS_CODE, expected=200),
                        TestAssertion(type=AssertionType.TITLE_CONTAINS, expected="Test"),
                    ],
                ),
            ],
        )

        report = await executor.execute_scenario(scenario)
        step = report.step_results[0]
        assert len(step.assertion_results) == 2
        assert step.assertion_results[0].passed is True  # status_code matches
        assert step.assertion_results[1].passed is True  # title contains "Test"

    async def test_assertion_failure_fails_step(
        self,
        executor: ScenarioExecutor,
    ) -> None:
        """Basarisiz assertion adimi fail eder."""
        scenario = TestScenario(
            name="Assertion Fail",
            steps=[
                ScenarioStep(
                    name="Load",
                    type=StepType.PAGE_LOAD,
                    url="https://example.com",
                    assertions=[
                        TestAssertion(type=AssertionType.STATUS_CODE, expected=404),
                    ],
                ),
            ],
        )

        report = await executor.execute_scenario(scenario)
        assert report.step_results[0].passed is False
        assert report.step_results[0].assertion_results[0].passed is False

    async def test_base_url_applied(
        self,
        executor: ScenarioExecutor,
        mock_runner: AsyncMock,
    ) -> None:
        """Base URL goreceli URL'lere eklenir."""
        scenario = TestScenario(
            name="Base URL Test",
            base_url="https://example.com",
            steps=[
                ScenarioStep(
                    name="Load",
                    type=StepType.PAGE_LOAD,
                    url="/page",
                ),
            ],
        )

        await executor.execute_scenario(scenario)
        call_args = mock_runner.execute.call_args
        assert call_args[0][1]["url"] == "https://example.com/page"

    async def test_step_params_forwarded(
        self,
        executor: ScenarioExecutor,
        mock_runner: AsyncMock,
    ) -> None:
        """Step params runner'a iletilir."""
        scenario = TestScenario(
            name="Params Test",
            steps=[
                ScenarioStep(
                    name="Element Check",
                    type=StepType.CHECK_ELEMENT,
                    url="https://example.com",
                    params={"selector": "#main", "timeout": 5},
                ),
            ],
        )

        await executor.execute_scenario(scenario)
        call_args = mock_runner.execute.call_args
        assert call_args[0][1]["selector"] == "#main"
        assert call_args[0][1]["timeout"] == 5

    async def test_exception_in_step_handled(
        self,
        executor: ScenarioExecutor,
        mock_runner: AsyncMock,
    ) -> None:
        """Adim calistirmada exception yakalanir."""
        mock_runner.execute.side_effect = RuntimeError("unexpected")

        scenario = TestScenario(
            name="Exception Test",
            steps=[
                ScenarioStep(
                    name="Error Step",
                    type=StepType.PAGE_LOAD,
                    url="https://example.com",
                ),
            ],
        )

        report = await executor.execute_scenario(scenario)
        assert report.passed is False
        assert "Beklenmeyen hata" in (report.step_results[0].error or "")

    async def test_report_timing(
        self,
        executor: ScenarioExecutor,
    ) -> None:
        """Rapor zamanlama bilgisi icerir."""
        scenario = TestScenario(
            name="Timing Test",
            steps=[
                ScenarioStep(
                    name="Step",
                    type=StepType.PAGE_LOAD,
                    url="https://example.com",
                ),
            ],
        )

        report = await executor.execute_scenario(scenario)
        assert report.started_at != ""
        assert report.finished_at != ""
        assert report.duration_ms >= 0


# --- ScenarioExecutor.execute_suite Tests ---


class TestExecuteSuite:
    """ScenarioExecutor.execute_suite() testleri."""

    async def test_execute_suite(
        self,
        executor: ScenarioExecutor,
    ) -> None:
        """Suite calistirmasi dogru rapor uretir."""
        scenarios = [
            TestScenario(
                name="Scenario 1",
                steps=[
                    ScenarioStep(
                        name="Step 1",
                        type=StepType.PAGE_LOAD,
                        url="https://example.com",
                    ),
                ],
            ),
            TestScenario(
                name="Scenario 2",
                steps=[
                    ScenarioStep(
                        name="Step 2",
                        type=StepType.PAGE_LOAD,
                        url="https://example.com",
                    ),
                ],
            ),
        ]

        suite_report = await executor.execute_suite(scenarios, suite_name="Test Suite")
        assert suite_report.suite_name == "Test Suite"
        assert suite_report.total_scenarios == 2
        assert suite_report.passed_scenarios == 2
        assert suite_report.failed_scenarios == 0

    async def test_suite_with_failures(
        self,
        executor: ScenarioExecutor,
        mock_runner: AsyncMock,
    ) -> None:
        """Suite'de basarisiz senaryo dogru raporlanir."""
        call_count = 0

        async def side_effect(_action: str, _params: dict[str, object]) -> dict[str, object]:
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                return {"success": False, "error": "fail"}
            return {"success": True, "page_title": "OK"}

        mock_runner.execute.side_effect = side_effect

        scenarios = [
            TestScenario(
                name="Pass",
                steps=[ScenarioStep(name="S1", type=StepType.PAGE_LOAD, url="https://a.com")],
            ),
            TestScenario(
                name="Fail",
                steps=[ScenarioStep(name="S2", type=StepType.PAGE_LOAD, url="https://b.com")],
            ),
        ]

        suite_report = await executor.execute_suite(scenarios)
        assert suite_report.passed_scenarios == 1
        assert suite_report.failed_scenarios == 1
