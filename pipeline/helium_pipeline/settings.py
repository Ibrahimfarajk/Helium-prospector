"""Settings via env vars (pydantic-settings)."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ─── Supabase ────────────────────────────────────────────────
    SUPABASE_URL: str = Field(default="")
    SUPABASE_SERVICE_ROLE_KEY: str = Field(default="")

    # ─── Pipeline tuning ─────────────────────────────────────────
    PIPELINE_USER_AGENT: str = Field(
        default=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        )
    )
    PIPELINE_RATE_LIMIT_MIN_SECONDS: float = 8.0
    PIPELINE_RATE_LIMIT_MAX_SECONDS: float = 12.0
    PIPELINE_MAX_RUNTIME_MINUTES: int = 60
    PIPELINE_MAX_PAGES_PER_RUN: int = 50  # Sicherheits-Cap

    # ─── Notifications ───────────────────────────────────────────
    DISCORD_WEBHOOK_URL: str = Field(default="")

    # ─── Dev / Test ──────────────────────────────────────────────
    HEADLESS: bool = True
    LOG_LEVEL: str = "INFO"


settings = Settings()
