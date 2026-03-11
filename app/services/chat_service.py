"""Chat service — orchestrates session, translation, execution, and insights."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional

from app.core.llm import LLMClient, get_llm_client
from app.schemas.chat import ChatMessageRequest, ChatMessageResponse
from app.services.adapters import get_adapter
from app.services.session_store import Session, get_session_store
from app.services.translator import QueryTranslator

logger = logging.getLogger(__name__)


class ChatService:
    """Central orchestrator for the chat flow:

    1. Load session
    2. Translate user message → query
    3. Optionally execute the query
    4. Optionally generate an insight from results
    5. Store exchange in session history
    """

    def __init__(self, llm_client: Optional[LLMClient] = None) -> None:
        self._llm = llm_client or get_llm_client()
        self._translator = QueryTranslator(self._llm)

    def handle_message(
        self,
        session: Session,
        request: ChatMessageRequest,
    ) -> ChatMessageResponse:
        """Process a single user message within a session."""

        # ── 1. Record user message ───────────────────────────────────────
        session.add_message("user", request.message)

        query: Optional[str] = None
        query_result: Optional[Any] = None
        insight: Optional[str] = None
        content: str = ""

        # ── 2. Determine if this is a data question or casual message ────
        # If the user is providing query results, skip translation
        if request.query_result is not None:
            # User executed the query externally and provided results
            query_result = request.query_result
            content = "Received your query results."

            if request.generate_insight:
                insight = self._translator.generate_insight(
                    session=session,
                    user_message=request.message,
                    query="(user-provided)",
                    query_result=query_result,
                )
                content = insight
        else:
            # Translate the message into a query
            try:
                result = self._translator.translate(session, request.message)
                query = result.query
                content = result.explanation or "Here is the generated query."

                # If the LLM returned an error or no query, treat as conversational
                if not query and result.raw_response.get("error"):
                    content = result.raw_response.get("error", content)
                elif not query:
                    # The LLM may have responded conversationally
                    content = result.explanation or result.raw_response.get("response", "")
                    if not content:
                        content = json.dumps(result.raw_response)

            except Exception as exc:
                logger.exception("Translation failed for session %s", session.session_id)
                content = f"Sorry, I encountered an error translating your question: {exc}"
                query = None

            # ── 3. Optionally execute ────────────────────────────────────
            if query and request.execute_query and session.has_db_connection:
                try:
                    adapter = get_adapter(session.query_type, session.db_url)
                    if adapter is not None:
                        query_result = adapter.execute(query)
                        adapter.close()
                except PermissionError as exc:
                    content += f"\n⚠️ Execution blocked: {exc}"
                except Exception as exc:
                    logger.exception("Query execution failed")
                    content += f"\n⚠️ Execution error: {exc}"

            # ── 4. Optionally generate insight ───────────────────────────
            if query_result is not None and request.generate_insight:
                try:
                    insight = self._translator.generate_insight(
                        session=session,
                        user_message=request.message,
                        query=query or "",
                        query_result=query_result,
                    )
                    content = insight
                except Exception as exc:
                    logger.exception("Insight generation failed")
                    insight = f"Could not generate insight: {exc}"

        # ── 5. Build and store assistant response ────────────────────────
        response = ChatMessageResponse(
            role="assistant",
            content=content,
            query=query,
            query_result=query_result,
            insight=insight,
            timestamp=datetime.utcnow(),
        )

        # Store the assistant message in session history
        session.add_message(
            "assistant",
            content,
            query=query,
            query_result=query_result,
            insight=insight,
        )

        return response


# ── Singleton accessor ───────────────────────────────────────────────────

_chat_service: Optional[ChatService] = None


def get_chat_service() -> ChatService:
    """Return the global chat service (lazily created)."""
    global _chat_service
    if _chat_service is None:
        _chat_service = ChatService()
    return _chat_service
