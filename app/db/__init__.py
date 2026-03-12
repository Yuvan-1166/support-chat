"""Database configuration and session maker.

Targets Aiven MySQL via PyMySQL (``mysql+pymysql://...``).

Connection-pool strategy
------------------------
* ``pool_pre_ping=True``   — test every connection before handing it out;
                              silently reconnects after a server-side timeout.
* ``pool_recycle=1800``    — recycle connections every 30 min so they never
                              hit MySQL's ``wait_timeout`` (Aiven default: 3600s).
* ``pool_size=5``          — keep 5 warm connections per worker.
* ``max_overflow=10``      — allow up to 10 extra connections under burst load.

SSL strategy
------------
* If ``DB_SSL_CA`` is set → use the Aiven-provided CA certificate for full
  TLS chain verification (most secure).
* Otherwise              → rely on PyMySQL's built-in TLS with server-side
  certificate validation (still encrypted, no manual cert management required).

Lazy initialisation
-------------------
The engine is created on the first call to ``get_engine()`` / ``get_db()``.
This prevents import-time crashes when ``DATABASE_URL`` is not yet set
(e.g. in the test suite, which overrides ``get_db`` via dependency injection).
"""

from __future__ import annotations

import logging
import ssl
import threading
from typing import Generator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# ── Thread-safe lazy singletons ───────────────────────────────────────────

_engine: Engine | None = None
_session_factory: sessionmaker | None = None
_lock = threading.Lock()


# ── SSL / connect-args helper ─────────────────────────────────────────────

def _build_connect_args(db_url: str, ssl_ca: str) -> dict:
    """Return driver-level ``connect_args`` appropriate for the database dialect.

    Parameters
    ----------
    db_url:
        Full SQLAlchemy connection URL (used to detect the dialect).
    ssl_ca:
        Optional path to the Aiven CA certificate.  Empty string means
        "use platform trust-store but still require TLS."
    """
    dialect = db_url.split("://")[0].split("+")[0].lower()

    if dialect != "mysql":
        return {}

    if ssl_ca:
        # Full chain verification with CA cert.
        ssl_ctx = ssl.create_default_context(cafile=ssl_ca)
        ssl_ctx.check_hostname = True
        ssl_ctx.verify_mode = ssl.CERT_REQUIRED
        logger.info("MySQL SSL: using CA certificate at %s", ssl_ca)
        return {"ssl": ssl_ctx}

    # No explicit CA → PyMySQL TLS with platform trust-store.
    logger.info("MySQL SSL: using platform trust-store (ssl_disabled=False)")
    return {"ssl": {"ssl_disabled": False}}


# ── Engine factory ────────────────────────────────────────────────────────

def _create_engine_from_settings() -> Engine:
    """Validate settings and build the SQLAlchemy engine."""
    settings = get_settings()
    db_url = settings.DATABASE_URL

    if not db_url:
        raise RuntimeError(
            "DATABASE_URL is not configured.  Set it in your .env file:\n"
            "  DATABASE_URL=mysql+pymysql://<user>:<password>@<host>:<port>/<db>"
            "?ssl_disabled=False"
        )

    connect_args = _build_connect_args(db_url, settings.DB_SSL_CA)
    logger.info("Creating database engine for: %s", settings.db_url_safe)

    return create_engine(
        db_url,
        connect_args=connect_args,
        pool_pre_ping=True,    # Detect & replace stale connections automatically
        pool_recycle=1800,     # Recycle before MySQL's wait_timeout kicks in
        pool_size=5,           # Maintained warm connections per worker
        max_overflow=10,       # Extra connections allowed under burst load
        echo=False,            # SQL logging controlled via LOG_LEVEL=DEBUG in .env
    )


# ── Public accessors ──────────────────────────────────────────────────────

def get_engine() -> Engine:
    """Return the application engine, creating it on the first call.

    Thread-safe: uses a module-level lock so only one thread initialises
    the engine even under concurrent startup.
    """
    global _engine
    if _engine is None:
        with _lock:
            if _engine is None:  # double-checked locking
                _engine = _create_engine_from_settings()
    return _engine


def _get_session_factory() -> sessionmaker:
    """Return (or lazily create) the session factory bound to the engine."""
    global _session_factory
    if _session_factory is None:
        with _lock:
            if _session_factory is None:
                _session_factory = sessionmaker(
                    autocommit=False,
                    autoflush=False,
                    bind=get_engine(),
                )
    return _session_factory


# ── ORM base ─────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


# ── FastAPI dependency ────────────────────────────────────────────────────

def get_db() -> Generator[Session, None, None]:
    """Yield a DB session per request; roll back on error, always close."""
    db = _get_session_factory()()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
