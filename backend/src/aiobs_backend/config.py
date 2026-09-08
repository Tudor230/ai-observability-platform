"""Runtime configuration (12-factor, env-overridable)."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AIOBS_", extra="ignore")

    database_url: str = (
        "postgresql+psycopg://postgres:postgres@127.0.0.1:55432/aiobs"
    )
    db_connect_timeout_s: int = 10
    # API keys / admin bootstrap
    admin_api_key: str | None = None
    # Pricing seed
    seed_pricing: bool = True
    # Alert evaluation cadence (seconds) for the CLI/background loop
    alert_interval_s: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()