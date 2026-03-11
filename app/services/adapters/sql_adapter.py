"""SQL adapter — executes read-only SQL queries via SQLAlchemy."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.services.adapters.base import BaseAdapter

logger = logging.getLogger(__name__)

# Statements that must NEVER appear in user-generated queries.
_WRITE_KEYWORDS = {
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "ALTER",
    "TRUNCATE",
    "CREATE",
    "REPLACE",
    "GRANT",
    "REVOKE",
}


class SQLAdapter(BaseAdapter):
    """Execute SQL against any SQLAlchemy-supported database in read-only mode."""

    def __init__(self, db_url: str) -> None:
        self._engine: Engine = create_engine(
            db_url,
            pool_pre_ping=True,
            pool_size=2,
            max_overflow=3,
        )

    # ── helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _is_read_only(query: str) -> bool:
        """Reject any query that contains write / DDL keywords."""
        upper = query.upper().strip()
        first_word = upper.split()[0] if upper else ""
        if first_word in _WRITE_KEYWORDS:
            return False
        # Also check for inline writes (e.g. subselect with INSERT)
        for kw in _WRITE_KEYWORDS:
            if f" {kw} " in f" {upper} ":
                return False
        return True

    # ── public API ───────────────────────────────────────────────────────

    def execute(self, query: str) -> list[dict[str, Any]]:
        if not self._is_read_only(query):
            raise PermissionError(
                "Only read-only (SELECT) queries are allowed. "
                "Write operations are blocked."
            )

        logger.info("Executing SQL query: %s", query[:200])

        with self._engine.connect() as conn:
            result = conn.execute(text(query))
            columns = list(result.keys())
            rows = [dict(zip(columns, row)) for row in result.fetchall()]

        logger.info("SQL query returned %d rows", len(rows))
        return rows

    def close(self) -> None:
        self._engine.dispose()
        logger.debug("SQL engine disposed")
