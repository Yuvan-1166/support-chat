"""Adapter registry — maps query types to execution adapters."""

from __future__ import annotations

from typing import Optional

from app.schemas.session import QueryType
from app.services.adapters.base import BaseAdapter


def get_adapter(query_type: QueryType, db_url: Optional[str]) -> Optional[BaseAdapter]:
    """Return the appropriate adapter for the given *query_type*.

    Returns ``None`` when *db_url* is not provided (query-only mode).
    """
    if db_url is None:
        return None

    if query_type in (QueryType.SQL, QueryType.MYSQL, QueryType.POSTGRESQL, QueryType.SQLITE):
        from app.services.adapters.sql_adapter import SQLAdapter

        return SQLAdapter(db_url)

    if query_type == QueryType.MONGODB:
        from app.services.adapters.mongodb_adapter import MongoDBAdapter

        return MongoDBAdapter(db_url)

    if query_type == QueryType.PANDAS:
        from app.services.adapters.pandas_adapter import PandasAdapter

        return PandasAdapter(db_url)

    raise ValueError(f"No adapter available for query type: {query_type}")
