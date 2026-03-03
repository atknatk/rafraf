"""Unit tests for agent.testing.models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

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

# --- StepType Tests ---


class TestStepType:
    """StepType enum testleri."""

    def test_all_step_types_exist(self) -> None:
        """Tum beklenen StepType degerleri mevcut."""
        expected = {
            "page_load",
            "check_element",
            "fill_form",
            "take_screenshot",
            "wait_for_response",
            "visual_regression",
        }
        actual = {st.value for st in StepType}
        assert actual == expected

    def test_step_type_from_string(self) -> None:
        """String'den StepType olusturulabilir."""
        assert StepType("page_load") == StepType.PAGE_LOAD
        assert StepType("visual_regression") == StepType.VISUAL_REGRESSION


# --- AssertionType Tests ---


class TestAssertionType:
    """AssertionType enum testleri."""

    def test_all_assertion_types_exist(self) -> None:
        """Tum beklenen AssertionType degerleri mevcut."""
        expected = {
            "status_code",
            "title_contains",
            "title_equals",
            "element_exists",
            "element_visible",
            "element_text_contains",
            "element_text_equals",
            "load_time_under",
            "response_status",
            "screenshot_match",
        }
        actual = {at.value for at in AssertionType}
        assert actual == expected


# --- TestAssertion Tests ---


class TestTestAssertion:
    """TestAssertion model testleri."""

    def test_create_assertion_with_defaults(self) -> None:
        """Varsayilan tolerans ile assertion olusturulur."""
        assertion = TestAssertion(
            type=AssertionType.STATUS_CODE,
            expected=200,
        )
        assert assertion.type == AssertionType.STATUS_CODE
        assert assertion.expected == 200
        assert assertion.tolerance == 0.0

    def test_create_assertion_with_tolerance(self) -> None:
        """Ozel tolerans ile assertion olusturulur."""
        assertion = TestAssertion(
            type=AssertionType.SCREENSHOT_MATCH,
            expected=True,
            tolerance=0.05,
        )
        assert assertion.tolerance == 0.05

    def test_assertion_is_frozen(self) -> None:
        """Assertion modeli immutable."""
        assertion = TestAssertion(
            type=AssertionType.STATUS_CODE,
            expected=200,
        )
        with pytest.raises(ValidationError):
            assertion.type = AssertionType.TITLE_CONTAINS  # type: ignore[misc]

    def test_tolerance_range_validation(self) -> None:
        """Tolerance 0.0-1.0 arasi olmali."""
        with pytest.raises(ValidationError):
            TestAssertion(
                type=AssertionType.SCREENSHOT_MATCH,
                expected=True,
                tolerance=1.5,
            )

        with pytest.raises(ValidationError):
            TestAssertion(
                type=AssertionType.SCREENSHOT_MATCH,
                expected=True,
                tolerance=-0.1,
            )


# --- ScenarioStep Tests ---


class TestScenarioStep:
    """ScenarioStep model testleri."""

    def test_create_step_minimal(self) -> None:
        """Minimum parametrelerle adim olusturulur."""
        step = ScenarioStep(
            name="Test Step",
            type=StepType.PAGE_LOAD,
            url="https://example.com",
        )
        assert step.name == "Test Step"
        assert step.type == StepType.PAGE_LOAD
        assert step.url == "https://example.com"
        assert step.params == {}
        assert step.assertions == []

    def test_create_step_with_params(self) -> None:
        """Parametreli adim olusturulur."""
        step = ScenarioStep(
            name="Form Step",
            type=StepType.FILL_FORM,
            url="https://example.com/form",
            params={"fields": [{"selector": "#name", "value": "test"}]},
        )
        assert "fields" in step.params

    def test_create_step_with_assertions(self) -> None:
        """Assertion'li adim olusturulur."""
        step = ScenarioStep(
            name="Load Step",
            type=StepType.PAGE_LOAD,
            url="https://example.com",
            assertions=[
                TestAssertion(type=AssertionType.STATUS_CODE, expected=200),
                TestAssertion(type=AssertionType.TITLE_CONTAINS, expected="Example"),
            ],
        )
        assert len(step.assertions) == 2

    def test_step_is_frozen(self) -> None:
        """Step modeli immutable."""
        step = ScenarioStep(
            name="Test",
            type=StepType.PAGE_LOAD,
            url="https://example.com",
        )
        with pytest.raises(ValidationError):
            step.name = "Changed"  # type: ignore[misc]


# --- TestScenario Tests ---


class TestTestScenario:
    """TestScenario model testleri."""

    def test_create_scenario_minimal(self) -> None:
        """Minimum parametrelerle senaryo olusturulur."""
        scenario = TestScenario(name="Test Scenario")
        assert scenario.name == "Test Scenario"
        assert scenario.description == ""
        assert scenario.base_url == ""
        assert scenario.tags == []
        assert scenario.steps == []
        assert scenario.timeout_seconds == 120

    def test_create_scenario_full(self) -> None:
        """Tum parametrelerle senaryo olusturulur."""
        scenario = TestScenario(
            name="Full Scenario",
            description="Test aciklamasi",
            base_url="https://example.com",
            tags=["smoke", "regression"],
            steps=[
                ScenarioStep(
                    name="Step 1",
                    type=StepType.PAGE_LOAD,
                    url="/",
                ),
            ],
            timeout_seconds=60,
        )
        assert len(scenario.steps) == 1
        assert len(scenario.tags) == 2
        assert scenario.timeout_seconds == 60

    def test_timeout_range_validation(self) -> None:
        """Timeout 1-3600 arasi olmali."""
        with pytest.raises(ValidationError):
            TestScenario(name="Test", timeout_seconds=0)

        with pytest.raises(ValidationError):
            TestScenario(name="Test", timeout_seconds=3601)


# --- AssertionResult Tests ---


class TestAssertionResult:
    """AssertionResult model testleri."""

    def test_create_passing_result(self) -> None:
        """Basarili assertion sonucu olusturulur."""
        result = AssertionResult(
            assertion_type=AssertionType.STATUS_CODE,
            passed=True,
            expected=200,
            actual=200,
            message="Status code: beklenen=200, gerceklesen=200",
        )
        assert result.passed is True
        assert result.expected == 200
        assert result.actual == 200

    def test_create_failing_result(self) -> None:
        """Basarisiz assertion sonucu olusturulur."""
        result = AssertionResult(
            assertion_type=AssertionType.STATUS_CODE,
            passed=False,
            expected=200,
            actual=404,
        )
        assert result.passed is False


# --- TestStepResult Tests ---


class TestTestStepResult:
    """TestStepResult model testleri."""

    def test_create_passing_step_result(self) -> None:
        """Basarili adim sonucu olusturulur."""
        result = TestStepResult(
            step_name="Load Page",
            step_type=StepType.PAGE_LOAD,
            passed=True,
            duration_ms=250,
        )
        assert result.passed is True
        assert result.duration_ms == 250

    def test_create_failing_step_result(self) -> None:
        """Basarisiz adim sonucu olusturulur."""
        result = TestStepResult(
            step_name="Load Page",
            step_type=StepType.PAGE_LOAD,
            passed=False,
            error="Sayfa yuklenemedi",
        )
        assert result.passed is False
        assert result.error is not None

    def test_step_result_with_screenshot(self) -> None:
        """Screenshot bilgili adim sonucu olusturulur."""
        result = TestStepResult(
            step_name="Screenshot",
            step_type=StepType.TAKE_SCREENSHOT,
            passed=True,
            screenshot_url="https://s3.amazonaws.com/test.png",
        )
        assert result.screenshot_url is not None


# --- TestReport Tests ---


class TestTestReport:
    """TestReport model testleri."""

    def test_create_passing_report(self) -> None:
        """Basarili senaryo raporu olusturulur."""
        report = TestReport(
            scenario_name="Test Scenario",
            passed=True,
            total_steps=3,
            passed_steps=3,
            failed_steps=0,
            duration_ms=1500,
        )
        assert report.passed is True
        assert report.total_steps == 3

    def test_create_failing_report(self) -> None:
        """Basarisiz senaryo raporu olusturulur."""
        report = TestReport(
            scenario_name="Test Scenario",
            passed=False,
            total_steps=3,
            passed_steps=2,
            failed_steps=1,
            duration_ms=2000,
            error="1 adim basarisiz",
        )
        assert report.passed is False
        assert report.failed_steps == 1


# --- TestSuiteReport Tests ---


class TestTestSuiteReport:
    """TestSuiteReport model testleri."""

    def test_create_suite_report(self) -> None:
        """Suite raporu olusturulur."""
        suite = TestSuiteReport(
            suite_name="Smoke Tests",
            total_scenarios=5,
            passed_scenarios=4,
            failed_scenarios=1,
            total_duration_ms=10000,
        )
        assert suite.total_scenarios == 5
        assert suite.generated_at != ""

    def test_suite_report_generated_at_auto(self) -> None:
        """generated_at otomatik doldurulur."""
        suite = TestSuiteReport(
            suite_name="Test",
            total_scenarios=0,
            passed_scenarios=0,
            failed_scenarios=0,
            total_duration_ms=0,
        )
        assert suite.generated_at is not None
        assert len(suite.generated_at) > 0
