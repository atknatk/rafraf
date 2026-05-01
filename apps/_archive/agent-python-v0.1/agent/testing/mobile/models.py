"""Maestro mobile test modelleri - Pydantic v2 frozen modeller.

Flow konfigurasyonu, sonuc raporlama ve screenshot bilgisi icin
immutable domain modelleri.
"""

from __future__ import annotations

import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class MaestroTestPlatform(StrEnum):
    """Desteklenen mobil test platformlari."""

    IOS = "ios"
    ANDROID = "android"


class MaestroFlowConfig(BaseModel):
    """Tek bir Maestro flow testi konfigurasyonu.

    Attributes:
        name: Flow adi (raporlama icin).
        flow_file: YAML flow dosya yolu.
        platform: Hedef platform.
        timeout: Timeout suresi (saniye).
        cwd: Calisma dizini (opsiyonel).
        project_slug: Proje tanimlayicisi (S3 icin).
        tags: Filtreleme/gruplama etiketleri.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    flow_file: str
    platform: MaestroTestPlatform = MaestroTestPlatform.IOS
    timeout: int = Field(default=300, ge=10, le=600)
    cwd: str | None = None
    project_slug: str | None = None
    tags: list[str] = Field(default_factory=list)


class MaestroSuiteConfig(BaseModel):
    """Maestro test suite konfigurasyonu.

    Attributes:
        suite_name: Suite adi.
        flows: Flow konfigurasyonlari.
        stop_on_failure: Hata olunca dursun mu.
    """

    model_config = ConfigDict(frozen=True)

    suite_name: str = "default"
    flows: list[MaestroFlowConfig] = Field(default_factory=list)
    stop_on_failure: bool = False


class MaestroScreenshotInfo(BaseModel):
    """Screenshot bilgisi.

    Attributes:
        flow_name: Ait oldugu flow'un adi.
        url: S3 veya lokal URL.
        path: Lokal dosya yolu (S3 kullanilamazsa).
        timestamp: Alinma zamani.
    """

    model_config = ConfigDict(frozen=True)

    flow_name: str
    url: str | None = None
    path: str | None = None
    timestamp: str = Field(
        default_factory=lambda: datetime.datetime.now(tz=datetime.UTC).isoformat(),
    )


class MaestroFlowResult(BaseModel):
    """Tek bir flow'un calistirma sonucu.

    Attributes:
        flow_name: Flow adi.
        flow_file: Flow dosya yolu.
        platform: Kullanilan platform.
        success: Basarili mi.
        total_tests: Toplam test sayisi.
        passed_tests: Basarili test sayisi.
        failed_tests: Basarisiz test sayisi.
        duration_ms: Calisma suresi (milisaniye).
        error: Hata mesaji (varsa).
        timed_out: Zaman asimi oldu mu.
        screenshots: Screenshot bilgileri.
        raw_output: Ham Maestro CLI ciktisi.
    """

    model_config = ConfigDict(frozen=True)

    flow_name: str
    flow_file: str
    platform: MaestroTestPlatform
    success: bool
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    duration_ms: int = 0
    error: str | None = None
    timed_out: bool = False
    screenshots: list[MaestroScreenshotInfo] = Field(default_factory=list)
    raw_output: str | None = None


class MaestroSuiteReport(BaseModel):
    """Suite calistirma raporu.

    Attributes:
        suite_name: Suite adi.
        total_flows: Toplam flow sayisi.
        passed_flows: Basarili flow sayisi.
        failed_flows: Basarisiz flow sayisi.
        total_tests: Toplam test sayisi.
        passed_tests: Basarili test sayisi.
        failed_tests: Basarisiz test sayisi.
        total_duration_ms: Toplam calisma suresi.
        flow_results: Her flow'un sonucu.
        all_passed: Hepsi basarili mi.
        generated_at: Rapor olusturulma zamani.
    """

    model_config = ConfigDict(frozen=True)

    suite_name: str
    total_flows: int
    passed_flows: int
    failed_flows: int
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    total_duration_ms: int = 0
    flow_results: list[MaestroFlowResult] = Field(default_factory=list)
    all_passed: bool = False
    generated_at: str = Field(
        default_factory=lambda: datetime.datetime.now(tz=datetime.UTC).isoformat(),
    )
