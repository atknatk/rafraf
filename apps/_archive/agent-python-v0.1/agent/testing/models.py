"""Test senaryo modelleri - Pydantic v2 ile tanimlanmis frozen modeller.

Test senaryolari YAML veya JSON formatinda tanimlanir.
Bu modul tum senaryo, adim, assertion ve rapor modellerini icerir.
"""

from __future__ import annotations

import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class StepType(StrEnum):
    """Test adim tipleri."""

    PAGE_LOAD = "page_load"
    CHECK_ELEMENT = "check_element"
    FILL_FORM = "fill_form"
    TAKE_SCREENSHOT = "take_screenshot"
    WAIT_FOR_RESPONSE = "wait_for_response"
    VISUAL_REGRESSION = "visual_regression"


class AssertionType(StrEnum):
    """Assertion tipleri."""

    STATUS_CODE = "status_code"
    TITLE_CONTAINS = "title_contains"
    TITLE_EQUALS = "title_equals"
    ELEMENT_EXISTS = "element_exists"
    ELEMENT_VISIBLE = "element_visible"
    ELEMENT_TEXT_CONTAINS = "element_text_contains"
    ELEMENT_TEXT_EQUALS = "element_text_equals"
    LOAD_TIME_UNDER = "load_time_under"
    RESPONSE_STATUS = "response_status"
    SCREENSHOT_MATCH = "screenshot_match"


class TestAssertion(BaseModel):
    """Tek bir assertion tanimi.

    Attributes:
        type: Assertion tipi.
        expected: Beklenen deger.
        tolerance: Screenshot karsilastirma toleransi (0.0-1.0, sadece screenshot_match icin).
    """

    model_config = ConfigDict(frozen=True)

    type: AssertionType
    expected: str | int | float | bool
    tolerance: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Screenshot karsilastirma toleransi (0.0-1.0)",
    )


class ScenarioStep(BaseModel):
    """Test senaryosundaki tek bir adim.

    Attributes:
        name: Adim adi (raporlama icin).
        type: Adim tipi.
        url: Hedef URL.
        params: Adima ozel parametreler.
        assertions: Adim sonrasi yapilacak dogrulama kontrolleri.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    type: StepType
    url: str
    params: dict[str, object] = Field(default_factory=dict)
    assertions: list[TestAssertion] = Field(default_factory=list)


class TestScenario(BaseModel):
    """Tek bir test senaryosu.

    Attributes:
        name: Senaryo adi.
        description: Senaryo aciklamasi.
        base_url: Tum adimlar icin temel URL (adim URL'i goreceli ise eklenir).
        tags: Filtreleme icin etiketler.
        steps: Senaryo adimlari.
        timeout_seconds: Senaryo icin maksimum sure (saniye).
    """

    model_config = ConfigDict(frozen=True)

    name: str
    description: str = ""
    base_url: str = ""
    tags: list[str] = Field(default_factory=list)
    steps: list[ScenarioStep] = Field(default_factory=list)
    timeout_seconds: int = Field(default=120, ge=1, le=3600)


class TestStepResult(BaseModel):
    """Tek bir adimin sonucu.

    Attributes:
        step_name: Adim adi.
        step_type: Adim tipi.
        passed: Adim basarili mi.
        duration_ms: Calisma suresi (milisaniye).
        runner_result: PlaywrightRunner'dan donen ham sonuc.
        assertion_results: Her assertion icin sonuclar.
        error: Hata mesaji (varsa).
        screenshot_url: Screenshot URL'i (varsa).
        screenshot_base64: Screenshot base64 (varsa).
    """

    model_config = ConfigDict(frozen=True)

    step_name: str
    step_type: StepType
    passed: bool
    duration_ms: int = 0
    runner_result: dict[str, object] = Field(default_factory=dict)
    assertion_results: list[AssertionResult] = Field(default_factory=list)
    error: str | None = None
    screenshot_url: str | None = None
    screenshot_base64: str | None = None


class AssertionResult(BaseModel):
    """Tek bir assertion sonucu.

    Attributes:
        assertion_type: Assertion tipi.
        passed: Assertion basarili mi.
        expected: Beklenen deger.
        actual: Gerceklesen deger.
        message: Detay mesaji.
    """

    model_config = ConfigDict(frozen=True)

    assertion_type: AssertionType
    passed: bool
    expected: str | int | float | bool
    actual: str | int | float | bool | None = None
    message: str = ""


class TestReport(BaseModel):
    """Tek bir senaryo raporu.

    Attributes:
        scenario_name: Senaryo adi.
        passed: Tum adimlar basarili mi.
        total_steps: Toplam adim sayisi.
        passed_steps: Basarili adim sayisi.
        failed_steps: Basarisiz adim sayisi.
        duration_ms: Toplam calisma suresi.
        step_results: Adim sonuclari.
        started_at: Baslama zamani.
        finished_at: Bitis zamani.
        error: Genel hata mesaji (varsa).
    """

    model_config = ConfigDict(frozen=True)

    scenario_name: str
    passed: bool
    total_steps: int
    passed_steps: int
    failed_steps: int
    duration_ms: int
    step_results: list[TestStepResult] = Field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""
    error: str | None = None


class TestSuiteReport(BaseModel):
    """Birden fazla senaryo iceren suite raporu.

    Attributes:
        suite_name: Suite adi.
        total_scenarios: Toplam senaryo sayisi.
        passed_scenarios: Basarili senaryo sayisi.
        failed_scenarios: Basarisiz senaryo sayisi.
        total_duration_ms: Toplam calisma suresi.
        scenario_reports: Senaryo raporlari.
        generated_at: Rapor olusturma zamani.
    """

    model_config = ConfigDict(frozen=True)

    suite_name: str
    total_scenarios: int
    passed_scenarios: int
    failed_scenarios: int
    total_duration_ms: int
    scenario_reports: list[TestReport] = Field(default_factory=list)
    generated_at: str = Field(
        default_factory=lambda: datetime.datetime.now(tz=datetime.UTC).isoformat(),
    )


# Forward reference guncellemesi
TestStepResult.model_rebuild()
