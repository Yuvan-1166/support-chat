"""Application configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration sourced from .env / environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    # ── LLM ──────────────────────────────────────────────────────────────
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    # ── Application ──────────────────────────────────────────────────────
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"

    # ── Session ──────────────────────────────────────────────────────────
    SESSION_TTL_SECONDS: int = 3600  # 1 hour default

    # ── Security ─────────────────────────────────────────────────────────
    API_KEYS: str = ""  # comma-separated

    # ── Rate Limiting ────────────────────────────────────────────────────
    RATE_LIMIT: str = "60/minute"

    @property
    def api_key_list(self) -> list[str]:
        """Return API_KEYS split into a list, filtering out blanks."""
        return [k.strip() for k in self.API_KEYS.split(",") if k.strip()]

    @property
    def is_development(self) -> bool:
        return self.APP_ENV.lower() == "development"


@lru_cache
def get_settings() -> Settings:
    """Return a cached singleton ``Settings`` instance."""
    return Settings()
