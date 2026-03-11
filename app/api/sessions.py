"""Session management API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import require_api_key
from app.schemas.chat import ChatHistoryResponse, ChatMessageResponse
from app.schemas.session import (
    SessionCreateRequest,
    SessionCreateResponse,
    SessionInfoResponse,
)
from app.services.session_store import get_session_store

router = APIRouter(prefix="/sessions", tags=["Sessions"])


@router.post(
    "",
    response_model=SessionCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new chat session",
)
def create_session(
    body: SessionCreateRequest,
    _api_key: str = Depends(require_api_key),
):
    """Create a new session with schema context and optional DB connection."""
    store = get_session_store()
    session = store.create(
        query_type=body.query_type,
        schema_context=body.schema_context,
        db_url=body.db_url,
        system_instructions=body.system_instructions,
    )
    return SessionCreateResponse(
        session_id=session.session_id,
        created_at=session.created_at,
        query_type=session.query_type,
        has_db_connection=session.has_db_connection,
    )


@router.get(
    "/{session_id}",
    response_model=SessionInfoResponse,
    summary="Get session information",
)
def get_session(
    session_id: str,
    _api_key: str = Depends(require_api_key),
):
    """Retrieve session metadata and message count."""
    store = get_session_store()
    session = store.get(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found or expired.",
        )
    return SessionInfoResponse(
        session_id=session.session_id,
        created_at=session.created_at,
        query_type=session.query_type,
        message_count=len(session.messages),
        has_db_connection=session.has_db_connection,
    )


@router.get(
    "/{session_id}/history",
    response_model=ChatHistoryResponse,
    summary="Get full conversation history",
)
def get_session_history(
    session_id: str,
    _api_key: str = Depends(require_api_key),
):
    """Return all messages in the session's conversation history."""
    store = get_session_store()
    session = store.get(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found or expired.",
        )

    messages = [
        ChatMessageResponse(
            role=m["role"],
            content=m["content"],
            query=m.get("query"),
            query_result=m.get("query_result"),
            insight=m.get("insight"),
            timestamp=m.get("timestamp"),
        )
        for m in session.messages
    ]
    return ChatHistoryResponse(session_id=session.session_id, messages=messages)


@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a session",
)
def delete_session(
    session_id: str,
    _api_key: str = Depends(require_api_key),
):
    """Terminate a session and remove its conversation history."""
    store = get_session_store()
    deleted = store.delete(session_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found.",
        )
    return None
