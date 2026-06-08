"""FastAPI application entry-point."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
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
    """Open one connection to verify DB reachability and pre-fill the pool."""
    from sqlalchemy import text
    from app.db import get_engine

    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    logger.info("Database connection pool warmed up successfully.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown hooks."""
    setup_logging()

    # Warm the DB pool in a background thread.
    try:
        await asyncio.to_thread(_warm_db)
    except Exception as exc:
        logger.error(
            "DB warm-up failed — check DATABASE_URL / SSL cert config: %s", exc
        )

    # Mount MCP server after DB is ready.
    try:
        from app.db import get_db
        from app.mcp.server import mount_mcp_server
        from app.services.sql_session_store import get_session_store
        from app.services.translator import QueryTranslator
        from app.core.llm import get_llm_client

        db_gen = get_db()
        db = next(db_gen)
        session_store = get_session_store(db)
        translator = QueryTranslator(get_llm_client())
        mount_mcp_server(app, session_store, translator)
    except Exception as exc:
        logger.error("MCP server setup failed: %s", exc)

    yield
    # Future: close DB pools, Redis, etc.


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

app.add_middleware(RateLimitMiddleware, max_requests=60, window_seconds=60)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(AccessLogMiddleware, coloured=get_settings().is_development)

# ── Routers ──────────────────────────────────────────────────────────────

app.include_router(sessions.router)
app.include_router(chat.router)


@app.get("/", tags=["Root"])
def app_root():
    return {"Artifact": "Support Chat", "version": app.version}


@app.get("/health", tags=["System"])
def health_check():
    """Health check — returns 200 OK if service is running."""
    return {"status": "healthy", "version": "0.1.0"}
# Reload trigger comment

