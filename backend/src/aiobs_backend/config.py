"""Runtime configuration (12-factor, env-overridable)."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AIOBS_", extra="ignore")

    database_url: str = (
        "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/aiobs"
    )
    db_connect_timeout_s: int = 10
    # API keys / admin bootstrap
    admin_api_key: str | None = None
    # Read access (F06): when set, read endpoints require `x-api-key` (or the admin key)
    read_api_key: str | None = None
    # Ingest body cap (F21)
    max_ingest_bytes: int = 10 * 1024 * 1024
    # Pricing seed
    seed_pricing: bool = True
    # Alert evaluation cadence (seconds) for the CLI/background loop
    alert_interval_s: int = 60
    # Alert delivery (F37): POST created alerts as JSON to this webhook
    alert_webhook_url: str | None = None
    alert_webhook_timeout_s: float = 3.0
    # Data retention (F35): 0 keeps data forever; >0 purges older rows
    retention_days: int = 0
    # Threshold rules (F04) — evaluated per UTC day
    alert_min_executions: int = 5
    alert_error_rate: float = 0.5
    alert_daily_tokens: int = 2_000_000
    alert_p95_latency_ms: float = 30_000
    alert_tool_calls_per_execution: float = 20
    alert_cost_anomaly_factor: float = 3.0


@lru_cache
def get_settings() -> Settings:
    return Settings()