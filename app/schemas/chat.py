"""Pydantic schemas for chat message requests and responses (three-mode agent)."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class ChatMode(str, Enum):
    """The three operating modes of the assistant.

    * ``ask``       — RAG-grounded help & navigation (no DB, no actions).
    * ``visualize`` — read-only insight query → rows + chart spec.
    * ``agent``     — autonomous tool use to automate CRM features.
    """

    ASK = "ask"
    VISUALIZE = "visualize"
    AGENT = "agent"


class ChatMessageRequest(BaseModel):
    """Payload sent by the client (the CRM proxy) for each conversation turn."""

    message: str = Field(..., min_length=1, max_length=5000, description="The user's message")
    mode: ChatMode = Field(
        ChatMode.ASK,
        description="Which mode to handle this turn: ask | visualize | agent.",
    )
    confirmed: bool = Field(
        False,
        description=(
            "AGENT mode only. Set True to approve a previously returned "
            "`requires_confirmation` action so it actually executes."
        ),
    )


class VisualizationSpec(BaseModel):
    """Chart rendering hints the CRM frontend uses for VISUALIZE results."""

    chart_type: str = Field("table", description="bar|line|pie|area|scatter|table|number")
    x: Optional[str] = Field(None, description="Column for the x-axis / category")
    y: Optional[str] = Field(None, description="Column for the value / measure")
    aggregate: str = Field("none", description="sum|count|avg|none")
    title: Optional[str] = None
    row_count: int = 0


class PendingActionModel(BaseModel):
    """An AGENT action awaiting user confirmation."""

    tool: str
    tool_input: dict[str, Any] = Field(default_factory=dict)
    prompt: str


class ChatMessageResponse(BaseModel):
    """Single message returned to the client."""

    role: str = Field("assistant", description="Always 'assistant'")
    mode: ChatMode = Field(..., description="The mode that handled this turn")
    content: str = Field(..., description="Natural-language response text")

    # VISUALIZE
    query: Optional[str] = Field(None, description="The executed SELECT query")
    query_result: Optional[Any] = Field(None, description="Result rows of the query")
    visualization: Optional[VisualizationSpec] = Field(None, description="Chart spec for the UI")

    # AGENT
    agent_reasoning: Optional[list[dict[str, Any]]] = Field(
        None, description="(Agent mode) reasoning steps with tool calls"
    )
    tool_results: Optional[list[dict[str, Any]]] = Field(
        None, description="(Agent mode) raw tool outputs"
    )
    requires_confirmation: bool = Field(
        False, description="(Agent mode) True when an action awaits confirmation"
    )
    pending_action: Optional[PendingActionModel] = Field(
        None, description="(Agent mode) the action to confirm"
    )

    # Shared
    sources: Optional[list[dict[str, Any]]] = Field(
        None, description="(Ask mode) knowledge sources used for grounding"
    )
    error: Optional[str] = Field(None, description="Error detail when the turn failed")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ChatHistoryMessage(BaseModel):
    """A persisted message as stored in the session's history."""

    role: str
    content: str
    query: Optional[str] = None
    query_result: Optional[Any] = None
    insight: Optional[str] = None
    timestamp: Optional[Any] = None


class ChatHistoryResponse(BaseModel):
    """Full conversation history for a session."""

    session_id: str
    messages: list[ChatHistoryMessage]
