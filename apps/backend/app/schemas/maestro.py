"""Maestro mobile test integration Pydantic schemas.

Request/response modelleri: flow tanimlama, test calistirma,
sonuc raporlama ve screenshot rapor endpoint'leri icin.
"""

from __future__ import annotations

import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

# --- Enum Tanimlari ---


class MaestroPlatform(StrEnum):
    """Maestro test platformlari."""

    IOS = "ios"
    ANDROID = "android"


class MaestroFlowStatus(StrEnum):
    """Flow calistirma durumlari."""

    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    TIMEOUT = "timeout"


class MaestroRunStatus(StrEnum):
    """Test run toplam durumlari."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


# --- Request Modelleri ---


class MaestroFlowDefinition(BaseModel):
    """Tek bir Maestro flow tanimlamasi.

    Attributes:
        name: Flow adi (raporlama icin).
        flow_file: YAML flow dosya yolu (agent tarafinda).
        platform: Hedef platform (ios/android).
        timeout: Flow icin timeout suresi (saniye).
        tags: Filtreleme/gruplama etiketleri.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    flow_file: str
    platform: MaestroPlatform = MaestroPlatform.IOS
    timeout: int = Field(default=300, ge=10, le=600)
    tags: list[str] = Field(default_factory=list)


class RunFlowRequest(BaseModel):
    """Tek bir flow calistirma istegi.

    Attributes:
        flow_file: YAML flow dosya yolu.
        platform: Hedef platform.
        cwd: Calisma dizini (opsiyonel).
        timeout: Timeout suresi (saniye).
        project_slug: Proje tanimlayicisi (S3 path icin).
    """

    flow_file: str
    platform: MaestroPlatform = MaestroPlatform.IOS
    cwd: str | None = None
    timeout: int = Field(default=300, ge=10, le=600)
    project_slug: str | None = None


class RunSuiteRequest(BaseModel):
    """Birden fazla flow iceren suite calistirma istegi.

    Attributes:
        suite_name: Suite adi (raporlama icin).
        flows: Flow tanimlari listesi.
        project_slug: Proje tanimlayicisi.
        cwd: Calisma dizini (opsiyonel).
        stop_on_failure: Hata olunca dursun mu.
    """

    suite_name: str = "default"
    flows: list[MaestroFlowDefinition]
    project_slug: str | None = None
    cwd: str | None = None
    stop_on_failure: bool = False


class RunAllFlowsRequest(BaseModel):
    """Bir dizindeki tum flow'lari calistirma istegi.

    Attributes:
        flows_dir: Flow dosyalari dizini.
        platform: Hedef platform.
        cwd: Calisma dizini (opsiyonel).
        timeout: Timeout suresi (saniye).
        project_slug: Proje tanimlayicisi.
    """

    flows_dir: str
    platform: MaestroPlatform = MaestroPlatform.IOS
    cwd: str | None = None
    timeout: int = Field(default=300, ge=10, le=600)
    project_slug: str | None = None


class ValidateFlowRequest(BaseModel):
    """Flow dosyasi dogrulama istegi.

    Attributes:
        flow_file: Dogrulanacak flow dosya yolu.
    """

    flow_file: str


class TakeScreenshotRequest(BaseModel):
    """Screenshot alma istegi.

    Attributes:
        platform: Hedef platform.
        project_slug: Proje tanimlayicisi.
    """

    platform: MaestroPlatform = MaestroPlatform.IOS
    project_slug: str | None = None


class ListFlowsRequest(BaseModel):
    """Flow dosyalari listeleme istegi.

    Attributes:
        flows_dir: Taranacak dizin yolu.
    """

    flows_dir: str


# --- Response Modelleri ---


class FlowStepScreenshot(BaseModel):
    """Adim bazli screenshot bilgisi.

    Attributes:
        step_name: Adim adi.
        screenshot_url: S3 veya lokal URL.
        timestamp: Alinma zamani.
    """

    model_config = ConfigDict(frozen=True)

    step_name: str
    screenshot_url: str
    timestamp: str = Field(
        default_factory=lambda: datetime.datetime.now(tz=datetime.UTC).isoformat(),
    )


class FlowResult(BaseModel):
    """Tek bir flow'un calistirma sonucu.

    Attributes:
        flow_file: Flow dosya yolu.
        platform: Kullanilan platform.
        status: Calistirma durumu.
        total_tests: Toplam test sayisi.
        passed_tests: Basarili test sayisi.
        failed_tests: Basarisiz test sayisi.
        duration_ms: Calisma suresi (milisaniye).
        error: Hata mesaji (varsa).
        screenshots: Screenshot URL listesi.
        output: Maestro CLI ham ciktisi.
        timed_out: Zaman asimi oldu mu.
    """

    model_config = ConfigDict(frozen=True)

    flow_file: str
    platform: MaestroPlatform
    status: MaestroFlowStatus
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    duration_ms: int = 0
    error: str | None = None
    screenshots: list[str] = Field(default_factory=list)
    output: str | None = None
    timed_out: bool = False


class RunFlowResponse(BaseModel):
    """Tek bir flow calistirma yaniti.

    Attributes:
        success: Basarili mi.
        result: Flow sonucu.
    """

    model_config = ConfigDict(frozen=True)

    success: bool
    result: FlowResult


class SuiteResult(BaseModel):
    """Suite calistirma sonucu.

    Attributes:
        suite_name: Suite adi.
        status: Toplam durum.
        total_flows: Toplam flow sayisi.
        passed_flows: Basarili flow sayisi.
        failed_flows: Basarisiz flow sayisi.
        total_tests: Toplam test sayisi.
        passed_tests: Basarili test sayisi.
        failed_tests: Basarisiz test sayisi.
        duration_ms: Toplam calisma suresi.
        flow_results: Her flow'un sonucu.
        screenshots: Tum screenshot'lar.
    """

    model_config = ConfigDict(frozen=True)

    suite_name: str
    status: MaestroRunStatus
    total_flows: int
    passed_flows: int
    failed_flows: int
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    duration_ms: int = 0
    flow_results: list[FlowResult] = Field(default_factory=list)
    screenshots: list[str] = Field(default_factory=list)


class RunSuiteResponse(BaseModel):
    """Suite calistirma yaniti.

    Attributes:
        success: Basarili mi.
        result: Suite sonucu.
    """

    model_config = ConfigDict(frozen=True)

    success: bool
    result: SuiteResult


class ValidateFlowResponse(BaseModel):
    """Flow dogrulama yaniti.

    Attributes:
        valid: Flow gecerli mi.
        flow_file: Dogrulanan dosya yolu.
        file_size_bytes: Dosya boyutu (byte).
        has_known_commands: Bilinen Maestro komutlari iceriyor mu.
        error: Hata mesaji (varsa).
    """

    model_config = ConfigDict(frozen=True)

    valid: bool
    flow_file: str
    file_size_bytes: int = 0
    has_known_commands: bool = False
    error: str | None = None


class ScreenshotResponse(BaseModel):
    """Screenshot alma yaniti.

    Attributes:
        success: Basarili mi.
        screenshot_url: S3 URL (varsa).
        screenshot_path: Lokal dosya yolu (fallback).
        platform: Platform.
        error: Hata mesaji (varsa).
    """

    model_config = ConfigDict(frozen=True)

    success: bool
    screenshot_url: str | None = None
    screenshot_path: str | None = None
    platform: MaestroPlatform
    error: str | None = None


class FlowFileInfo(BaseModel):
    """Flow dosyasi bilgisi.

    Attributes:
        name: Dosya adi.
        path: Tam dosya yolu.
        size_bytes: Dosya boyutu.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    path: str
    size_bytes: int


class ListFlowsResponse(BaseModel):
    """Flow listesi yaniti.

    Attributes:
        success: Basarili mi.
        flows_dir: Taranan dizin yolu.
        flow_count: Bulunan flow sayisi.
        flows: Flow dosyalari listesi.
        error: Hata mesaji (varsa).
    """

    model_config = ConfigDict(frozen=True)

    success: bool
    flows_dir: str
    flow_count: int = 0
    flows: list[FlowFileInfo] = Field(default_factory=list)
    error: str | None = None


class MaestroTestReport(BaseModel):
    """Test sonuc raporu (CI entegrasyonu icin).

    Attributes:
        run_id: Unique calistirma kimligi.
        suite_name: Suite adi.
        status: Toplam durum.
        total_flows: Toplam flow sayisi.
        passed_flows: Basarili flow sayisi.
        failed_flows: Basarisiz flow sayisi.
        total_tests: Toplam test sayisi.
        passed_tests: Basarili test sayisi.
        failed_tests: Basarisiz test sayisi.
        duration_ms: Toplam calisma suresi.
        flow_results: Her flow'un detayli sonucu.
        screenshots: Screenshot bilgileri.
        generated_at: Rapor olusturulma zamani.
    """

    model_config = ConfigDict(frozen=True)

    run_id: str
    suite_name: str
    status: MaestroRunStatus
    total_flows: int
    passed_flows: int
    failed_flows: int
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    duration_ms: int = 0
    flow_results: list[FlowResult] = Field(default_factory=list)
    screenshots: list[FlowStepScreenshot] = Field(default_factory=list)
    generated_at: str = Field(
        default_factory=lambda: datetime.datetime.now(tz=datetime.UTC).isoformat(),
    )
