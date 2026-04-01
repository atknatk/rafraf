"""Application configuration via Pydantic Settings."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# .env dosyasini repo root'ta veya CWD'de ara
_ENV_FILES: list[str] = []
try:
    _repo_root_env = Path(__file__).resolve().parents[4] / ".env"
    if _repo_root_env.exists():
        _ENV_FILES.append(str(_repo_root_env))
except IndexError:
    pass  # Docker container — path hierarchy is shorter
_ENV_FILES.append(".env")


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "RafRaf Backend"
    app_version: str = "0.1.0"
    debug: bool = False

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/rafraf"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Security
    jwt_secret_key: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 7

    # Rate Limiting
    rate_limit_requests_per_minute: int = 10

    # External APIs
    anthropic_api_key: str = ""
    deepgram_api_key: str = ""
    openai_api_key: str = ""

    # AWS
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_s3_bucket: str = ""
    aws_region: str = "eu-central-1"

    # Bedrock
    use_bedrock: bool = True

    # WebSocket
    ws_heartbeat_interval: int = 30
    ws_heartbeat_timeout: int = 10

    # GitHub
    github_token: str = ""
    github_webhook_secret: str = ""

    # Agent
    agent_api_key: str = ""

    # Claude AI Orchestrator
    claude_default_model: str = "claude-sonnet-4-5-20250929"
    claude_simple_model: str = "claude-haiku-4-5-20251001"
    claude_complex_model: str = "claude-opus-4-5-20250929"
    claude_max_iterations: int = 10
    claude_max_tokens: int = 4096

    # Approval
    approval_timeout_seconds: int = 300

    # --- Claude Code (claude -p) ---
    claude_code_enabled: bool = True
    claude_code_binary: str = "claude"
    claude_code_project_dir: str = ""  # Bos ise subprocess CWD kullanilir; Docker'da /opt/rafraf
    claude_code_default_dir: str = ""  # Proje secilmemisse kullanilacak varsayilan dizin
    claude_code_max_turns: int = 30
    claude_code_model: str = "sonnet"
    claude_code_timeout_seconds: int = 300
    claude_code_fallback_to_api: bool = True

    # Subscription Usage Alerts
    subscription_daily_message_limit: int = 200  # Claude Max gunluk mesaj limiti (tahmini)
    subscription_warning_threshold: float = 0.8  # %80 esik

    # APNs Push Notifications
    apns_key_path: str = ""
    apns_key_id: str = ""
    apns_team_id: str = ""
    apns_bundle_id: str = "com.rafraf.app"
    apns_use_sandbox: bool = True

    # Conversation Memory
    conversation_ttl_seconds: int = 86400  # 24 hours
    conversation_max_tokens: int = 50000  # Context window token limit


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return cached application settings singleton."""
    global _settings  # noqa: PLW0603
    if _settings is None:
        _settings = Settings()
    return _settings
