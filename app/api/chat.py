"""Chat API endpoint — send messages, receive queries and insights."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session as DBSession

from app.core.security import require_api_key
from app.db import get_db
from app.schemas.chat import ChatMessageRequest, ChatMessageResponse
from app.services.agent_service import get_agent_service
from app.services.chat_service import get_chat_service
from app.services.sql_session_store import get_session_store
from app.services.translator import QueryTranslator
from app.core.llm import get_llm_client

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
    db: DBSession = Depends(get_db),
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
    5. If ``agent_mode`` is ``True``, the agent runs multi-step reasoning
       and can execute queries, create tasks, etc.
    """
    store = get_session_store(db)
    session = store.get(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found or expired.",
        )

    # Check if agent mode is requested
    if body.agent_mode:
        # Use agent service for multi-step reasoning
        translator = QueryTranslator(get_llm_client())
        agent_service = get_agent_service(store, translator)
        agent_response = agent_service.run_agent(
            session=session,
            user_message=body.message,
            max_steps=10,
        )

        # Record user message
        store.add_message(session.session_id, "user", body.message)

        # Convert agent response to ChatMessageResponse format
        response = ChatMessageResponse(
            role="assistant",
            content=agent_response.content,
            agent_reasoning=[
                step.model_dump() for step in agent_response.agent_reasoning
            ],
        )

        # Record assistant message
        store.add_message(
            session_id=session.session_id,
            role="assistant",
            content=agent_response.content,
        )

        return response
    else:
        # Use standard chat service for simple query translation
        chat_service = get_chat_service()
        response = chat_service.handle_message(store, session, body)
        return response
