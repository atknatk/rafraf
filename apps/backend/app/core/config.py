"""Application configuration via Pydantic Settings."""

from datetime import datetime
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

    # Security — JWT (T2.9: RS256 migration with HS256 grace period)
    #
    # As of T2.9 (Faz 2), the backend signs JWTs with RS256 (asymmetric).
    # ``jwt_private_key_path`` and ``jwt_public_key_path`` point to PEM files
    # on disk (in dev: ``./secrets/jwt_*.pem``; in prod: AWS Secrets Manager
    # / Kubernetes Secrets, mounted as a file).
    #
    # ``jwt_legacy_hs256_secret`` is the OLD HS256 shared secret retained for
    # token *verification only* during the grace period. ``jwt_legacy_grace_until``
    # is the cutover deadline — after this UTC timestamp, HS256 tokens are
    # rejected with ``legacy_hs256_token_rejected_post_grace``.
    #
    # ``jwt_secret_key`` is DEPRECATED (kept for backward compat / legacy HS256
    # signing during transition). Will be removed after the grace period ends.
    # DEPRECATED — use jwt_legacy_hs256_secret instead.
    jwt_secret_key: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "RS256"  # T2.9: was HS256
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 7
    jwt_private_key_path: str | None = None  # PEM, RS256 sign
    jwt_public_key_path: str | None = None  # PEM, RS256 verify
    jwt_legacy_hs256_secret: str | None = None  # grace period verify only
    jwt_legacy_grace_until: datetime | None = None  # UTC cutover deadline

    # Rate Limiting
    rate_limit_requests_per_minute: int = 10

    # External APIs
    anthropic_api_key: str = ""

    # AWS
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_s3_bucket: str = ""
    aws_region: str = "eu-central-1"

    # WebSocket
    ws_heartbeat_interval: int = 30
    ws_heartbeat_timeout: int = 10

    # GitHub
    github_token: str = ""
    github_webhook_secret: str = ""

    # Agent
    # DEPRECATED (T1.3): shared-secret auth for the legacy Python host agent /
    # the current Go bridge transition. Will be removed in T1.x in favour of
    # per-bridge ``pairing_token`` (alembic 014). Keep populated until then or
    # the WebSocket endpoint at ``/ws/agent`` will reject all bridges.
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
    apns_bundle_id: str = "com.atknatk.rafraf"
    apns_use_sandbox: bool = True

    # Conversation Memory
    conversation_ttl_seconds: int = 86400  # 24 hours
    conversation_max_tokens: int = 50000  # Context window token limit

    # Readiness probe
    # When True, /ready also requires at least one bridge to be online.
    # Default is False so bare-startup readiness (DB+Redis only) succeeds in
    # dev/CI; flip to True in production for stricter readiness gating.
    ready_requires_bridge: bool = False


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return cached application settings singleton."""
    global _settings  # noqa: PLW0603
    if _settings is None:
        _settings = Settings()
    return _settings
