"""Application configuration via Pydantic Settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
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


def get_settings() -> Settings:
    """Return application settings singleton."""
    return Settings()
