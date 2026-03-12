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

import base64
import logging
import os
import ssl
import tempfile
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

# Holds the path to a tempfile written from DB_SSL_CA_B64 so it persists
# for the lifetime of the process without being re-created on every call.
_ssl_ca_tempfile: tempfile.NamedTemporaryFile | None = None


def _resolve_ssl_ca(ssl_ca: str, ssl_ca_b64: str) -> str:
    """Return a usable CA cert file path, or empty string if none configured.

    Priority: DB_SSL_CA_B64 (base64 env var) > DB_SSL_CA (file path).
    """
    global _ssl_ca_tempfile

    if ssl_ca_b64:
        # Decode the base64 PEM and write to a persistent temp file.
        if _ssl_ca_tempfile is None:
            raw = base64.b64decode(ssl_ca_b64)
            _ssl_ca_tempfile = tempfile.NamedTemporaryFile(
                prefix="aiven_ca_", suffix=".pem", delete=False
            )
            _ssl_ca_tempfile.write(raw)
            _ssl_ca_tempfile.flush()
            logger.info("MySQL SSL: decoded DB_SSL_CA_B64 → %s", _ssl_ca_tempfile.name)
        return _ssl_ca_tempfile.name

    if ssl_ca:
        if not os.path.isfile(ssl_ca):
            raise FileNotFoundError(
                f"DB_SSL_CA is set to '{ssl_ca}' but the file does not exist.\n"
                "For containerised / cloud deployments use DB_SSL_CA_B64 instead:\n"
                "  base64 -w0 ca.pem   # copy the output into the env var on Render"
            )
        return ssl_ca

    return ""


def _build_connect_args(db_url: str, ssl_ca: str, ssl_ca_b64: str = "") -> dict:
    """Return driver-level ``connect_args`` appropriate for the database dialect.

    Parameters
    ----------
    db_url:    Full SQLAlchemy connection URL (dialect detected from prefix).
    ssl_ca:    Path to CA certificate file (local dev).
    ssl_ca_b64: Base64-encoded CA certificate content (cloud/container).
    """
    dialect = db_url.split("://")[0].split("+")[0].lower()

    if dialect != "mysql":
        return {}

    ca_path = _resolve_ssl_ca(ssl_ca, ssl_ca_b64)

    if ca_path:
        ssl_ctx = ssl.create_default_context(cafile=ca_path)
        ssl_ctx.check_hostname = True
        ssl_ctx.verify_mode = ssl.CERT_REQUIRED
        logger.info("MySQL SSL: CA certificate loaded from %s", ca_path)
        return {"ssl": ssl_ctx}

    # No CA cert → rely on platform trust-store (connection still encrypted).
    logger.info("MySQL SSL: using platform trust-store (no CA cert specified)")
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

    connect_args = _build_connect_args(db_url, settings.DB_SSL_CA, settings.DB_SSL_CA_B64)
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
