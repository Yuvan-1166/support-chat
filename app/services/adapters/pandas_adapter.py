"""Pandas adapter — executes DataFrame queries in a sandboxed manner."""

from __future__ import annotations

import json
import logging
from typing import Any

import pandas as pd

from app.services.adapters.base import BaseAdapter

logger = logging.getLogger(__name__)


class PandasAdapter(BaseAdapter):
    """Execute Pandas queries against an in-memory DataFrame.

    The DataFrame must be loaded from a CSV / JSON URL or raw data
    provided at session creation.  For safety, only ``df.query()``
    expressions are supported (no arbitrary ``eval``).
    """

    def __init__(self, db_url: str) -> None:
        """Load a DataFrame from the given URL / path.

        Supports CSV and JSON formats.  The *db_url* is expected to be
        a file path or HTTP URL ending in ``.csv`` or ``.json``.
        """
        lower = db_url.lower()
        if lower.endswith(".json"):
            self._df = pd.read_json(db_url)
        elif lower.endswith(".csv"):
            self._df = pd.read_csv(db_url)
        else:
            # Default to CSV
            self._df = pd.read_csv(db_url)
        logger.info("Pandas adapter loaded DataFrame with shape %s", self._df.shape)

    def execute(self, query: str) -> list[dict[str, Any]]:
        """Execute a JSON-encoded Pandas query.

        Expected format from the LLM::

            {
                "expression": "score > 5",
                "columns": ["name", "score"],    // optional
                "limit": 100                     // optional
            }
        """
        try:
            spec = json.loads(query)
        except json.JSONDecodeError:
            # Try direct df.query() expression as plain string
            spec = {"expression": query}

        expression = spec.get("expression", "")
        columns = spec.get("columns")
        limit = int(spec.get("limit", 100))

        if not expression:
            raise ValueError("Pandas query must specify an 'expression'.")

        result_df = self._df.query(expression)

        if columns:
            result_df = result_df[columns]

        result_df = result_df.head(limit)
        rows = result_df.to_dict(orient="records")

        logger.info("Pandas query returned %d rows", len(rows))
        return rows

    def close(self) -> None:
        logger.debug("Pandas adapter released")
