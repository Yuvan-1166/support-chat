"""Pydantic schemas for session-related requests and responses."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ── Enums ────────────────────────────────────────────────────────────────


class QueryType(str, Enum):
    """Supported query dialects."""

    SQL = "sql"
    MYSQL = "mysql"
    POSTGRESQL = "postgresql"
    SQLITE = "sqlite"
    MONGODB = "mongodb"
    PANDAS = "pandas"


# ── Schema description models ───────────────────────────────────────────


class SchemaField(BaseModel):
    """Describes a single column / field in a table or collection."""

    name: str = Field(..., description="Column or field name")
    type: str = Field(..., description="Data type, e.g. INT, VARCHAR(255), ObjectId")
    description: Optional[str] = Field(None, description="Human-readable description")
    is_primary_key: bool = Field(False, description="Whether this is the primary key")


class SchemaTable(BaseModel):
    """Describes a table, collection, or DataFrame."""

    name: str = Field(..., description="Table / collection name")
    fields: list[SchemaField] = Field(..., description="Columns / fields in this table")
    description: Optional[str] = Field(None, description="What this table represents")


# ── Request / Response ──────────────────────────────────────────────────


class SessionCreateRequest(BaseModel):
    """Payload to create a new chat session."""

    query_type: QueryType = Field(
        ...,
        description="Target query language for this session",
    )
    schema_context: list[SchemaTable] = Field(
        ...,
        description="Tables / collections the LLM should know about",
    )
    db_url: Optional[str] = Field(
        None,
        description=(
            "Database connection URL.  When provided the service can execute "
            "generated queries directly.  Omit to receive query strings only."
        ),
    )
    system_instructions: Optional[str] = Field(
        None,
        description="Extra instructions or business rules for the LLM",
    )


class SessionCreateResponse(BaseModel):
    """Returned after successfully creating a session."""

    session_id: str
    created_at: datetime
    query_type: QueryType
    has_db_connection: bool


class SessionInfoResponse(BaseModel):
    """Summary information about an existing session."""

    session_id: str
    created_at: datetime
    query_type: QueryType
    message_count: int
    has_db_connection: bool
