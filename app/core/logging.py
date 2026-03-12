"""Structured logging configuration."""

from __future__ import annotations

import logging
import sys

from app.core.config import get_settings


def setup_logging() -> None:
    """Configure root logger and wire uvicorn loggers through our formatter.

    Called both at module import-time and inside the lifespan hook so that
    the configuration survives uvicorn's own ``logging.config.dictConfig``
    call that runs during startup.
    """
    settings = get_settings()

    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    if settings.is_development:
        formatter = logging.Formatter(
            "%(asctime)s │ %(levelname)-8s │ %(name)s │ %(message)s",
            datefmt="%H:%M:%S",
        )
    else:
        formatter = logging.Formatter(
            '{"ts":"%(asctime)s","level":"%(levelname)s",'
            '"logger":"%(name)s","msg":"%(message)s"}',
        )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    # ── Root logger ───────────────────────────────────────────────────────
    root = logging.getLogger()
    root.setLevel(log_level)
    root.handlers = [handler]   # replace any pre-existing handlers

    # ── Uvicorn loggers ───────────────────────────────────────────────────
    # Uvicorn installs its own handlers; remove them so records bubble up
    # to our root handler (and our formatter) instead of being duplicated.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers = []          # remove uvicorn's default handlers
        uv_logger.propagate = True       # let root handler print them
        uv_logger.setLevel(log_level)    # honour our configured level

    # ── Third-party noise ─────────────────────────────────────────────────
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.INFO if settings.is_development else logging.WARNING
    )
