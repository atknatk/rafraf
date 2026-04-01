"""Agent konfigurasyonu - environment variables ve varsayilan degerler."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# .env dosyasini birden fazla konumda ara:
# 1. ~/.rafraf-agent/.env (installed daemon)
# 2. CWD/.env (development)
_ENV_FILES: list[str] = []
_home_env = Path.home() / ".rafraf-agent" / ".env"
if _home_env.exists():
    _ENV_FILES.append(str(_home_env))
_ENV_FILES.append(".env")


class AgentConfig(BaseSettings):
    """Host Agent konfigurasyonu.

    Environment variable'lardan veya .env dosyasindan okunur.
    """

    model_config = SettingsConfigDict(
        env_prefix="AGENT_",
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
    )

    host_id: str = Field(
        description="Benzersiz host kimlik bilgisi (ornek: macbook-pro)",
    )
    api_key: str = Field(
        description="Backend auth icin API anahtari",
    )
    backend_ws_url: str = Field(
        description="Backend WebSocket adresi (wss://...)",
    )
    heartbeat_interval: int = Field(
        default=30,
        ge=5,
        le=300,
        description="Heartbeat gonderme araligi (saniye)",
    )
    reconnect_initial_delay: float = Field(
        default=1.0,
        ge=0.1,
        le=10.0,
        description="Ilk reconnect bekleme suresi (saniye)",
    )
    reconnect_max_delay: float = Field(
        default=60.0,
        ge=1.0,
        le=300.0,
        description="Maksimum reconnect bekleme suresi (saniye)",
    )
    version: str = Field(
        default="0.4.0",
        description="Agent yazilim surumu",
    )

    # Resource monitor settings
    resource_report_interval: int = Field(
        default=60,
        ge=10,
        le=600,
        description="Kaynak raporu gonderme araligi (saniye)",
    )
    alarm_cpu_threshold: float = Field(
        default=90.0,
        ge=0.0,
        le=100.0,
        description="CPU alarm esik degeri (%)",
    )
    alarm_memory_threshold: float = Field(
        default=85.0,
        ge=0.0,
        le=100.0,
        description="Memory alarm esik degeri (%)",
    )
    alarm_disk_threshold: float = Field(
        default=90.0,
        ge=0.0,
        le=100.0,
        description="Disk alarm esik degeri (%)",
    )

    # Project discovery settings
    project_config_path: str = Field(
        default="projects.yaml",
        description="YAML proje konfigurasyonu dosya yolu",
    )
    project_scan_paths: list[str] = Field(
        default_factory=list,
        description="Git repo taramasi yapilacak dizin listesi",
    )
    project_scan_depth: int = Field(
        default=2,
        ge=1,
        le=5,
        description="Dizin tarama derinligi",
    )
    project_sync_interval: int = Field(
        default=300,
        ge=60,
        le=3600,
        description="Proje senkronizasyon araligi (saniye)",
    )

    # Capability flags
    capability_docker: bool = Field(default=False, description="Docker destegi")
    capability_playwright: bool = Field(default=False, description="Playwright destegi")
    capability_maestro_ios: bool = Field(default=False, description="Maestro iOS destegi")
    capability_maestro_android: bool = Field(default=False, description="Maestro Android destegi")
    capability_shell: bool = Field(default=True, description="Shell destegi")
    capability_xcode_build: bool = Field(default=False, description="Xcode build destegi")
    capability_android_build: bool = Field(default=False, description="Android build destegi")
    capability_git: bool = Field(default=True, description="Git destegi")
    capability_python: bool = Field(default=True, description="Python destegi")
    capability_nodejs: bool = Field(default=False, description="Node.js destegi")
    capability_claude_code: bool = Field(default=True, description="Claude Code destegi")

    # Claude Code settings
    claude_binary: str = Field(default="claude", description="claude CLI binary path")
    claude_timeout_seconds: int = Field(
        default=600, ge=60, le=3600, description="Claude process timeout (saniye)"
    )

    def get_capabilities(self) -> list[str]:
        """Aktif yeteneklerin listesini dondurur."""
        capability_map: dict[str, bool] = {
            "docker": self.capability_docker,
            "playwright": self.capability_playwright,
            "maestro_ios": self.capability_maestro_ios,
            "maestro_android": self.capability_maestro_android,
            "shell": self.capability_shell,
            "xcode_build": self.capability_xcode_build,
            "android_build": self.capability_android_build,
            "git": self.capability_git,
            "python": self.capability_python,
            "nodejs": self.capability_nodejs,
            "claude_code": self.capability_claude_code,
        }
        return [name for name, enabled in capability_map.items() if enabled]
