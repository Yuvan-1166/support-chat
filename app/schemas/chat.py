"""Pydantic schemas for chat message requests and responses."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field


class ChatMessageRequest(BaseModel):
    """Payload sent by the client for each conversation turn."""

    message: str = Field(
        ...,
        min_length=1,
        description="The user's natural-language message",
    )
    execute_query: bool = Field(
        False,
        description=(
            "When True *and* the session has a db_url, the generated query "
            "will be executed and results returned."
        ),
    )
    generate_insight: bool = Field(
        False,
        description="When True, pass query results back to the LLM for a natural-language summary",
    )
    query_result: Optional[Any] = Field(
        None,
        description=(
            "If the client executed the query externally, provide the result "
            "here so the bot can generate insights from it."
        ),
    )


class ChatMessageResponse(BaseModel):
    """Single message returned to the client."""

    role: str = Field(..., description="'user' or 'assistant'")
    content: str = Field(..., description="Natural-language response text")
    query: Optional[str] = Field(None, description="Generated data query, if applicable")
    query_result: Optional[Any] = Field(None, description="Result of executing the query")
    insight: Optional[str] = Field(None, description="Natural-language insight from the results")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ChatHistoryResponse(BaseModel):
    """Full conversation history for a session."""

    session_id: str
    messages: list[ChatMessageResponse]
