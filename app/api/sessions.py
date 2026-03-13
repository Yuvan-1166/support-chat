"""Session management API endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session as DBSession

from app.core.security import require_api_key
from app.db import get_db
from app.schemas.chat import ChatHistoryResponse, ChatMessageResponse
from app.schemas.session import (
    QueryType,
    SessionCreateRequest,
    SessionCreateResponse,
    SessionInfoResponse,
)
from app.services.schema_introspector import introspect_schema
from app.services.sql_session_store import get_session_store

router = APIRouter(prefix="/sessions", tags=["Sessions"])
logger = logging.getLogger(__name__)

_SQL_QUERY_TYPES = {
    QueryType.SQL,
    QueryType.MYSQL,
    QueryType.POSTGRESQL,
    QueryType.SQLITE,
}


@router.post(
    "",
    response_model=SessionCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new chat session",
)
def create_session(
    body: SessionCreateRequest,
    _api_key: str = Depends(require_api_key),
    db: DBSession = Depends(get_db),
):
    """Create a new session with schema context and optional DB connection."""
    schema_context = body.schema_context

    if body.db_url and body.query_type in _SQL_QUERY_TYPES:
        try:
            discovered = introspect_schema(body.query_type, body.db_url)
            if discovered:
                schema_context = discovered
                logger.info("Using auto-discovered schema for new session")
            elif not schema_context:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "No tables discovered from the provided db_url. "
                        "Provide schema_context manually or check DB permissions."
                    ),
                )
        except HTTPException:
            raise
        except Exception as exc:
            if not schema_context:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Failed to auto-discover schema from db_url: {exc}. "
                        "Provide schema_context manually or fix the DB URL/permissions."
                    ),
                )
            logger.warning(
                "Schema auto-discovery failed; using provided schema_context instead: %s",
                exc,
            )

    if not schema_context:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="schema_context is required when auto-discovery is unavailable.",
        )

    store = get_session_store(db)
    session = store.create(
        query_type=body.query_type,
        schema_context=schema_context,
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
    db: DBSession = Depends(get_db),
):
    """Retrieve session metadata and message count."""
    store = get_session_store(db)
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
    db: DBSession = Depends(get_db),
):
    """Return all messages in the session's conversation history."""
    store = get_session_store(db)
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
    db: DBSession = Depends(get_db),
):
    """Terminate a session and remove its conversation history."""
    store = get_session_store(db)
    deleted = store.delete(session_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found.",
        )
    return None
