"""Chat API endpoint — send messages, receive queries and insights."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import require_api_key
from app.schemas.chat import ChatMessageRequest, ChatMessageResponse
from app.services.chat_service import get_chat_service
from app.services.session_store import get_session_store

router = APIRouter(prefix="/sessions", tags=["Chat"])


@router.post(
    "/{session_id}/chat",
    response_model=ChatMessageResponse,
    summary="Send a chat message",
)
def send_message(
    session_id: str,
    body: ChatMessageRequest,
    _api_key: str = Depends(require_api_key),
):
    """Submit a natural-language message and receive a generated query,
    optional execution results, and optional natural-language insight.

    **Flow**:
    1. The message is translated into a data query matching the session's
       ``query_type`` and ``schema_context``.
    2. If ``execute_query`` is ``True`` and the session has a ``db_url``,
       the query is executed and results are returned.
    3. If the caller executed the query externally, they can provide
       ``query_result`` in the request body.
    4. If ``generate_insight`` is ``True`` and results exist, the LLM
       produces a plain-English summary.
    """
    store = get_session_store()
    session = store.get(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found or expired.",
        )

    chat_service = get_chat_service()
    response = chat_service.handle_message(session, body)
    return response
