"""MCP Resource context models for Support Chat.

These Pydantic models define the shape of data returned when the agent
reads MCP resources. The actual resource registration happens in
app/mcp/server.py via FastMCP @mcp.resource() decorators.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


class SessionContext(BaseModel):
    """MCP representation of a chat session's context."""

    session_id: str
    query_type: str
    has_db_connection: bool
    system_instructions: Optional[str] = None
    message_count: int
    schema_context: list[dict[str, Any]]


class Contact(BaseModel):
    """Represents a single CRM contact (placeholder)."""

    id: str
    name: str
    email: str
    status: str
    score: int
