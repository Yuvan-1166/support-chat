"""SQL adapter — executes read-only SQL queries via SQLAlchemy."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url

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
        normalized_url = self._normalize_db_url(db_url)
        self._engine: Engine = create_engine(
            normalized_url,
            pool_pre_ping=True,
            pool_size=2,
            max_overflow=3,
        )

    @staticmethod
    def _normalize_db_url(db_url: str) -> str:
        """Normalize incoming DB URLs so SQLAlchemy picks a supported driver.

        Key rule:
        - ``mysql://...`` defaults to ``mysqldb`` (MySQLdb), which is not
          installed in our runtime image.
        - Force MySQL URLs to ``mysql+pymysql://...``.
        """
        parsed = make_url(db_url)
        driver = parsed.drivername.lower()

        if driver == "mysql" or driver == "mysql+mysqldb":
            logger.info("Normalizing MySQL DB URL driver to mysql+pymysql")
            parsed = parsed.set(drivername="mysql+pymysql")

        return parsed.render_as_string(hide_password=False)

    # ── helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _is_read_only(query: str) -> bool:
        """Reject any query that contains write / DDL keywords."""
        upper = query.upper().strip()
        first_word = upper.split()[0] if upper else ""
        if first_word in _WRITE_KEYWORDS:
            return False
        # Block stacked statements (e.g. "SELECT ...; DROP TABLE ...")
        if ";" in upper[:-1]:
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
            rows = [dict(row) for row in result.mappings().all()]

        logger.info("SQL query returned %d rows", len(rows))
        return rows

    def close(self) -> None:
        self._engine.dispose()
        logger.debug("SQL engine disposed")
