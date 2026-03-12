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

    # ── Database ─────────────────────────────────────────────────────────
    # Full SQLAlchemy URL.  For Aiven MySQL use the format:
    #   mysql+pymysql://<user>:<password>@<host>:<port>/<dbname>?ssl_disabled=False
    DATABASE_URL: str = ""

    # Optional absolute path to the Aiven-provided CA certificate.
    # When set, full TLS chain verification is performed.
    # Leave empty to rely on the platform/system trust-store (still TLS-required).
    DB_SSL_CA: str = ""

    # ── Rate Limiting ────────────────────────────────────────────────────
    RATE_LIMIT: str = "60/minute"

    @property
    def api_key_list(self) -> list[str]:
        """Return API_KEYS split into a list, filtering out blanks."""
        return [k.strip() for k in self.API_KEYS.split(",") if k.strip()]

    @property
    def is_development(self) -> bool:
        return self.APP_ENV.lower() == "development"

    @property
    def db_url_safe(self) -> str:
        """DATABASE_URL with password redacted — safe for logging."""
        import re
        return re.sub(r"(?<=://)([^:]+):([^@]+)@", r"\1:***@", self.DATABASE_URL)


@lru_cache
def get_settings() -> Settings:
    """Return a cached singleton ``Settings`` instance."""
    return Settings()
