"""Simple in-memory rate limiter middleware (no external dependency)."""

from __future__ import annotations

import time
from collections import defaultdict

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Fixed-window rate limiter keyed by client IP.

    Parameters
    ----------
    max_requests : int
        Maximum requests allowed per *window_seconds*.
    window_seconds : int
        Size of the fixed time window in seconds.
    """

    def __init__(self, app, *, max_requests: int = 60, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        # {ip: [(timestamp, count)]}
        self._hits: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next) -> Response:
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        cutoff = now - self.window_seconds

        # Purge old entries
        self._hits[client_ip] = [
            t for t in self._hits[client_ip] if t > cutoff
        ]

        if len(self._hits[client_ip]) >= self.max_requests:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Try again later."},
            )

        self._hits[client_ip].append(now)
        return await call_next(request)
