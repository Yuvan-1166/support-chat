"""Structured logging configuration."""

from __future__ import annotations

import logging
import sys

from app.core.config import get_settings

# ── ANSI colour codes ─────────────────────────────────────────────────────

_RESET  = "\033[0m"
_BOLD   = "\033[1m"
_DIM    = "\033[2m"
_GREEN  = "\033[32m"
_YELLOW = "\033[33m"
_RED    = "\033[31m"
_CYAN   = "\033[36m"
_BLUE   = "\033[34m"
_GREY   = "\033[90m"

_LEVEL_COLOURS: dict[int, str] = {
    logging.DEBUG:    _CYAN,
    logging.INFO:     _GREEN,
    logging.WARNING:  _YELLOW,
    logging.ERROR:    _RED,
    logging.CRITICAL: _BOLD + _RED,
}


class _ColourFormatter(logging.Formatter):
    """Dev formatter: coloured log-level, dimmed logger name, plain message."""

    _FMT = "{grey}{time}{reset} │ {colour}{level:<8}{reset} │ {dim}{name}{reset} │ {msg}"

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        colour = _LEVEL_COLOURS.get(record.levelno, "")
        time   = self.formatTime(record, self.datefmt)
        msg    = record.getMessage()
        if record.exc_info:
            msg += "\n" + self.formatException(record.exc_info)
        return self._FMT.format(
            grey=_GREY, reset=_RESET, dim=_DIM,
            time=time,
            colour=colour,
            level=record.levelname,
            name=record.name,
            msg=msg,
        )


def setup_logging() -> None:
    """Configure root logger and wire uvicorn loggers through our formatter.

    Called both at module import-time and inside the lifespan hook so that
    the configuration survives uvicorn's own ``logging.config.dictConfig``
    call that runs during startup.
    """
    settings = get_settings()

    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    if settings.is_development:
        formatter: logging.Formatter = _ColourFormatter(datefmt="%H:%M:%S")
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
    # Remove uvicorn's own handlers so our formatter is used instead.
    # uvicorn.access is silenced — AccessLogMiddleware replaces it with
    # richer, coloured one-liners.
    for name in ("uvicorn", "uvicorn.error"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers = []
        uv_logger.propagate = True
        uv_logger.setLevel(log_level)

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)  # muted — see AccessLogMiddleware

    # ── Third-party noise ─────────────────────────────────────────────────
    # SQLAlchemy emits per-statement logs at INFO; only show them on DEBUG.
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.DEBUG if settings.LOG_LEVEL.upper() == "DEBUG" else logging.WARNING
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("watchfiles").setLevel(logging.WARNING)
