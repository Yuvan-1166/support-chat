"""Structured logging configuration."""

from __future__ import annotations

import logging
import sys

from app.core.config import get_settings


def setup_logging() -> None:
    """Configure root logger based on application settings."""
    settings = get_settings()

    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    formatter: logging.Formatter
    if settings.is_development:
        formatter = logging.Formatter(
            "%(asctime)s │ %(levelname)-8s │ %(name)s │ %(message)s",
            datefmt="%H:%M:%S",
        )
    else:
        # JSON-ish single-line format for production log aggregators
        formatter = logging.Formatter(
            '{"ts":"%(asctime)s","level":"%(levelname)s",'
            '"logger":"%(name)s","msg":"%(message)s"}',
        )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(log_level)
    # Avoid duplicate handlers on repeated calls
    root.handlers = [handler]

    # Quieten noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
