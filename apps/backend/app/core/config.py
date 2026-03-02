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
    jwt_access_token_expire_minutes: int = 30

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

    # Agent
    agent_api_key: str = ""


def get_settings() -> Settings:
    """Return application settings singleton."""
    return Settings()
