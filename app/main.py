"""FastAPI application entry-point."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import chat, sessions
from app.core.access_log import AccessLogMiddleware
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.core.rate_limiter import RateLimitMiddleware

# Apply logging config at import-time so it takes effect before uvicorn
# installs its own handlers during startup.
setup_logging()

logger = logging.getLogger(__name__)


# ── Lifecycle ────────────────────────────────────────────────────────────


def _warm_db() -> None:
    """Open one connection to verify DB reachability and pre-fill the pool.

    Called in a thread-pool executor so the event loop is not blocked
    during the SSL + TCP handshake to the remote database.
    """
    from sqlalchemy import text

    from app.db import get_engine

    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    logger.info("Database connection pool warmed up successfully.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown hooks."""
    # Re-apply after uvicorn may have overwritten the config during startup.
    setup_logging()

    # Warm the DB pool in a background thread — avoids blocking the event
    # loop during the SSL handshake to the remote Aiven MySQL host.
    try:
        await asyncio.to_thread(_warm_db)
    except Exception as exc:
        logger.error(
            "DB warm-up failed — check DATABASE_URL / SSL cert config: %s", exc
        )

    yield
    # Cleanup resources on shutdown (future: close DB pools, Redis, etc.)


# ── App instance ─────────────────────────────────────────────────────────

app = FastAPI(
    title="Support Chat API",
    description=(
        "Natural-language → data-query translation service with "
        "session management, optional query execution, and insight generation."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# ── Middleware ───────────────────────────────────────────────────────────

# Rate limiting (in-memory, fixed-window, 60 req/min per IP)
app.add_middleware(RateLimitMiddleware, max_requests=60, window_seconds=60)

# CORS — allow all origins in development; tighten in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Access logging — outermost so it captures every request including
# rate-limited (429) and CORS-rejected ones.
app.add_middleware(AccessLogMiddleware, coloured=get_settings().is_development)

# ── Routers ──────────────────────────────────────────────────────────────

app.include_router(sessions.router)
app.include_router(chat.router)


# ── Health check ─────────────────────────────────────────────────────────


@app.get("/health", tags=["System"])
def health_check():
    """Simple health-check endpoint."""
    return {"status": "healthy", "version": app.version}


# ── Global error handler ────────────────────────────────────────────────


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch unhandled exceptions and return a clean 500."""
    settings = get_settings()
    detail = str(exc) if settings.is_development else "Internal server error"
    return JSONResponse(status_code=500, content={"detail": detail})
