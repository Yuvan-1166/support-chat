"""Request / response access-log middleware.

Replaces the raw ``uvicorn.access`` lines with a single structured line per
request that shows method, path, status code, timing, and a clear ✓ / ✗
outcome marker — all coloured in development.

Example output (development):
    16:01:23 │ INFO     │ access │ ✓  201  POST  /sessions                   (48 ms)
    16:01:24 │ INFO     │ access │ ✓  200  GET   /sessions/abc/history        (6 ms)
    16:01:25 │ WARNING  │ access │ ✗  404  POST  /sessions/bad/chat           (5 ms)
    16:01:26 │ WARNING  │ access │ ✗  422  POST  /sessions                   (3 ms)
    16:01:27 │ ERROR    │ access │ ✗  500  POST  /sessions/abc/chat           (312 ms)
    16:01:28 │ INFO     │ access │ ✓  200  GET   /health                     (1 ms)
"""

from __future__ import annotations

import logging
import time

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger("access")

# ── ANSI helpers ──────────────────────────────────────────────────────────

_RESET  = "\033[0m"
_BOLD   = "\033[1m"
_DIM    = "\033[2m"
_GREEN  = "\033[32m"
_YELLOW = "\033[33m"
_RED    = "\033[31m"
_CYAN   = "\033[36m"
_WHITE  = "\033[37m"

# status code → (log level, tick/cross, colour for the status number)
def _classify(status: int) -> tuple[int, str, str]:
    if status < 300:
        return logging.INFO,    "✓", _GREEN
    if status < 400:
        return logging.INFO,    "→", _CYAN
    if status < 500:
        return logging.WARNING, "✗", _YELLOW
    return logging.ERROR,       "✗", _RED


class AccessLogMiddleware(BaseHTTPMiddleware):
    """Emit one structured log line per HTTP request."""

    def __init__(self, app: ASGIApp, *, coloured: bool = True) -> None:
        super().__init__(app)
        self._coloured = coloured

    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.perf_counter()

        try:
            response: Response = await call_next(request)
            status = response.status_code
        except Exception:
            elapsed_ms = (time.perf_counter() - start) * 1_000
            self._log(request.method, request.url.path, 500, elapsed_ms)
            raise

        elapsed_ms = (time.perf_counter() - start) * 1_000
        self._log(request.method, request.url.path, status, elapsed_ms)
        return response

    # ── formatting ────────────────────────────────────────────────────────

    def _log(self, method: str, path: str, status: int, ms: float) -> None:
        level, tick, status_colour = _classify(status)

        if self._coloured:
            method_str  = f"{_BOLD}{_WHITE}{method:<6}{_RESET}"
            path_str    = f"{_DIM}{path}{_RESET}"
            status_str  = f"{_BOLD}{status_colour}{status}{_RESET}"
            tick_str    = f"{_BOLD}{status_colour}{tick}{_RESET}"
            timing_str  = f"{_DIM}({ms:.0f} ms){_RESET}"
            msg = f"{tick_str}  {status_str}  {method_str}  {path_str:<45} {timing_str}"
        else:
            msg = f"{tick}  {status}  {method:<6}  {path:<45} ({ms:.0f} ms)"

        logger.log(level, msg)
