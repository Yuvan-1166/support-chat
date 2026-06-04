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
async def send_message(
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
       and can execute queries, create tasks, update contacts, etc.
    """
    store = get_session_store(db)
    session = store.get(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found or expired.",
        )

    if body.agent_mode:
        translator = QueryTranslator(get_llm_client())
        agent_service = get_agent_service(store, translator)

        # Record user message before running so it's in history for the agent.
        store.add_message(session.session_id, "user", body.message)

        # Run agent asynchronously to avoid blocking the event loop.
        agent_response = await agent_service.run_agent_async(
            session=session,
            user_message=body.message,
            max_steps=10,
        )

        # Extract query/result from the first successful execute_query step
        # so the standard response fields are also populated.
        extracted_query = None
        extracted_result = None
        for step in agent_response.final_tool_results:
            if step.get("tool") == "execute_query" and step.get("success"):
                data = step.get("data") or {}
                extracted_query = data.get("query")
                extracted_result = data.get("query_result")
                break

        response = ChatMessageResponse(
            role="assistant",
            content=agent_response.content,
            query=extracted_query,
            query_result=extracted_result,
            agent_reasoning=[
                step.model_dump() for step in agent_response.agent_reasoning
            ],
        )

        store.add_message(
            session_id=session.session_id,
            role="assistant",
            content=agent_response.content,
        )

        return response

    # Standard (non-agent) path — synchronous chat service.
    import asyncio
    chat_service = get_chat_service()
    response = await asyncio.to_thread(
        chat_service.handle_message, store, session, body
    )
    return response
