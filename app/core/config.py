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

    # Optional base64-encoded content of the Aiven CA certificate.
    # Use this in all environments instead of mounting a ca.pem file.
    # Generate with: base64 -w0 ca.pem
    DB_SSL_CA_B64: str = ""

    # ── Rate Limiting ────────────────────────────────────────────────────
    RATE_LIMIT: str = "60/minute"

    # ── CRM Integration ──────────────────────────────────────────────────
    # Base URL of the CRM REST API that AGENT-mode tools call back into.
    CRM_BASE_URL: str = "http://localhost:3000"
    # Shared secret used to *verify* the employee JWT forwarded by the CRM's
    # /api/assistant proxy.  When blank, the JWT is decoded WITHOUT signature
    # verification (the CRM is treated as a trusted caller) — set this in any
    # environment where the service is reachable beyond the CRM.
    JWT_SECRET: str = ""
    JWT_ALGORITHMS: str = "HS256"  # comma-separated list

    # ── Agent ────────────────────────────────────────────────────────────
    AGENT_MAX_STEPS: int = 10

    # ── RAG (ASK mode) ───────────────────────────────────────────────────
    # Local sentence-transformers model — runs in-process, no API key.
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    CHROMA_DIR: str = "./.chroma"
    CHROMA_COLLECTION: str = "crm_knowledge"
    # Folder of docs (.md/.txt) ingested into the RAG store for ASK mode.
    KNOWLEDGE_DOCS_DIR: str = "./knowledge"
    RAG_TOP_K: int = 5

    @property
    def api_key_list(self) -> list[str]:
        """Return API_KEYS split into a list, filtering out blanks."""
        return [k.strip() for k in self.API_KEYS.split(",") if k.strip()]

    @property
    def jwt_algorithms(self) -> list[str]:
        """Return JWT_ALGORITHMS split into a list, filtering out blanks."""
        return [a.strip() for a in self.JWT_ALGORITHMS.split(",") if a.strip()]

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
