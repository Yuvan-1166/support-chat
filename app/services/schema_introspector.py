"""Database schema introspection helpers used during session creation."""

from __future__ import annotations

import logging

from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.schemas.session import QueryType, SchemaField, SchemaTable
from app.utils.db_url import split_ssl_options_from_url

logger = logging.getLogger(__name__)


def _supports_sql_introspection(query_type: QueryType) -> bool:
    return query_type in {
        QueryType.SQL,
        QueryType.MYSQL,
        QueryType.POSTGRESQL,
        QueryType.SQLITE,
    }


def introspect_schema(
    query_type: QueryType,
    db_url: str,
    *,
    max_tables: int = 150,
) -> list[SchemaTable]:
    """Introspect table/column metadata from a SQL database URL.

    Returns an empty list when query type is non-SQL.
    Raises RuntimeError on SQL introspection failures.
    """
    if not _supports_sql_introspection(query_type):
        return []

    from app.db import _build_connect_args, _normalize_db_url

    clean_url, per_url_ca_b64, per_url_ssl_verify = split_ssl_options_from_url(db_url)
    normalized_url = _normalize_db_url(clean_url)
    settings = get_settings()
    connect_args = _build_connect_args(
        normalized_url,
        per_url_ca_b64 or settings.DB_SSL_CA_B64,
        True if per_url_ssl_verify is None else per_url_ssl_verify,
    )

    engine = create_engine(
        normalized_url,
        connect_args=connect_args,
        pool_pre_ping=True,
        pool_size=1,
        max_overflow=0,
        echo=False,
    )

    try:
        inspector = inspect(engine)
        table_names = inspector.get_table_names()
        if not table_names:
            return []

        tables: list[SchemaTable] = []
        for table_name in table_names[:max_tables]:
            columns = inspector.get_columns(table_name)
            pk_constraint = inspector.get_pk_constraint(table_name) or {}
            pk_columns = set(pk_constraint.get("constrained_columns") or [])

            fields = [
                SchemaField(
                    name=column["name"],
                    type=str(column.get("type", "UNKNOWN")),
                    description=(column.get("comment") or None),
                    is_primary_key=column["name"] in pk_columns,
                )
                for column in columns
            ]

            tables.append(
                SchemaTable(
                    name=table_name,
                    fields=fields,
                    description="Auto-discovered from database metadata",
                )
            )

        logger.info("Auto-discovered %d tables from database", len(tables))
        return tables
    except SQLAlchemyError as exc:
        raise RuntimeError(f"Schema introspection failed: {exc}") from exc
    finally:
        engine.dispose()
