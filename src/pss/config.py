"""Applikationskonfiguration fra miljøvariabler (.env)."""

from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _to_async_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql://") and "+asyncpg" not in url:
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def _to_sync_database_url(async_url: str) -> str:
    sync = async_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    if sync.startswith("postgres://"):
        sync = sync.replace("postgres://", "postgresql://", 1)
    if "localhost" not in sync and "127.0.0.1" not in sync and "sslmode=" not in sync:
        sep = "&" if "?" in sync else "?"
        sync = f"{sync}{sep}sslmode=require"
    return sync


class Settings(BaseSettings):
    """PSS-indstillinger. Felter læses fra `.env` i projektroden."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Polymarket
    polymarket_private_key: SecretStr | None = None
    polymarket_funder_address: str | None = None
    polymarket_signature_type: int = 3

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://pss:password@localhost:5432/pss",
    )
    database_url_sync: str = Field(
        default="postgresql://pss:password@localhost:5432/pss",
    )

    # Telegram
    telegram_bot_token: SecretStr | None = None
    telegram_chat_id: str | None = None

    # Eksterne datakilder
    fred_api_key: SecretStr | None = None
    twitter_bearer_token: SecretStr | None = None

    # Operationelle
    log_level: str = "INFO"
    log_format: Literal["auto", "console", "json"] = "auto"
    environment: Literal["development", "production"] = "development"
    bankroll_usd: float = 10_000.0

    @model_validator(mode="after")
    def normalize_database_urls(self) -> Self:
        """Railway/Timescale leverer ofte postgres:// — normalisér drivere + SSL."""
        self.database_url = _to_async_database_url(self.database_url)
        self.database_url_sync = _to_sync_database_url(self.database_url)
        return self

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def asyncpg_dsn(self) -> str:
        """DSN til asyncpg (uden SQLAlchemy-driver-prefix)."""
        return self.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
