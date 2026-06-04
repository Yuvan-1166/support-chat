"""MCP Tool input/output schemas for Support Chat.

These Pydantic models define the contract for each MCP tool exposed by the
server. They are used for documentation and validation; the actual
implementations live in app/mcp/server.py via FastMCP decorators.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# ── execute_query ────────────────────────────────────────────────────────

class ExecuteQueryInput(BaseModel):
    session_id: str = Field(..., description="The session to run the query against.")
    question: str = Field(..., description="Natural language question to translate and optionally execute.")
    translate_only: bool = Field(False, description="If true, only generate the query without executing it.")


class ExecuteQueryOutput(BaseModel):
    query: Optional[str] = None
    explanation: Optional[str] = None
    query_result: Optional[Any] = None
    note: Optional[str] = None
    error: Optional[str] = None


# ── search_schema ────────────────────────────────────────────────────────

class SearchSchemaInput(BaseModel):
    session_id: str = Field(..., description="The session whose schema to search.")
    search_term: Optional[str] = Field(None, description="Optional term to filter tables/fields by name.")


class SearchSchemaOutput(BaseModel):
    tables: list[dict[str, Any]] = Field(default_factory=list)
    query_type: Optional[str] = None
    note: Optional[str] = None


# ── get_context ──────────────────────────────────────────────────────────

class GetContextInput(BaseModel):
    session_id: str = Field(..., description="The session to retrieve context from.")
    last_n: int = Field(5, description="Number of most recent messages to return.")


class GetContextOutput(BaseModel):
    session_id: str
    query_type: str
    message_count: int
    recent_messages: list[dict[str, Any]] = Field(default_factory=list)


# ── create_task ──────────────────────────────────────────────────────────

class CreateTaskInput(BaseModel):
    session_id: str = Field(..., description="Session context for the operation.")
    title: str = Field(..., description="Title of the task.")
    description: Optional[str] = Field(None, description="Longer description of the task.")
    priority: str = Field("normal", description="Task priority: low, normal, or high.")


class CreateTaskOutput(BaseModel):
    task_id: Optional[str] = None
    status: str
    note: Optional[str] = None
    error: Optional[str] = None


# ── update_contact ───────────────────────────────────────────────────────

class UpdateContactInput(BaseModel):
    session_id: str = Field(..., description="Session context for the operation.")
    contact_id: str = Field(..., description="CRM contact ID to update.")
    fields: dict[str, Any] = Field(..., description="Fields to update on the contact.")


class UpdateContactOutput(BaseModel):
    contact_id: str
    status: str
    note: Optional[str] = None
    error: Optional[str] = None


# ── send_email ───────────────────────────────────────────────────────────

class SendEmailInput(BaseModel):
    session_id: str = Field(..., description="Session context for the operation.")
    to: str = Field(..., description="Recipient email address.")
    subject: str = Field(..., description="Email subject line.")
    body: str = Field(..., description="Email body content.")


class SendEmailOutput(BaseModel):
    message_id: Optional[str] = None
    status: str
    note: Optional[str] = None
    error: Optional[str] = None
