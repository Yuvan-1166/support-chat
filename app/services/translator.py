"""Query translator — converts natural language into data queries via the LLM."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from app.core.llm import LLMClient
from app.services.session_store import Session
from app.utils.prompt_builder import build_chat_messages, build_system_prompt

logger = logging.getLogger(__name__)


@dataclass
class TranslationResult:
    """Structured output from the translation step."""

    query: str
    explanation: str
    confidence: float
    raw_response: dict[str, Any]


class QueryTranslator:
    """Translates user messages into data queries using an LLM."""

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm = llm_client

    def translate(self, session: Session, user_message: str) -> TranslationResult:
        """Generate a data query from a natural-language *user_message*.

        Uses the session's schema context and conversation history to build
        a contextual prompt, then asks the LLM for a JSON response.
        """
        system_prompt = build_system_prompt(
            query_type=session.query_type,
            schema_context=session.schema_context,
            system_instructions=session.system_instructions,
        )

        messages = build_chat_messages(
            system_prompt=system_prompt,
            conversation_history=session.get_llm_history(),
            user_message=user_message,
        )

        logger.debug("Translating message for session %s", session.session_id)

        result = self._llm.chat_completion_json(messages, temperature=0.1)

        return TranslationResult(
            query=result.get("query", ""),
            explanation=result.get("explanation", ""),
            confidence=float(result.get("confidence", 0)),
            raw_response=result,
        )

    def generate_insight(
        self,
        session: Session,
        user_message: str,
        query: str,
        query_result: Any,
    ) -> str:
        """Given query results, produce a natural-language insight."""
        system_prompt = build_system_prompt(
            query_type=session.query_type,
            schema_context=session.schema_context,
            system_instructions=session.system_instructions,
        )

        # Build a context message that includes the query and its result
        context = (
            f"The user asked: \"{user_message}\"\n"
            f"The generated query was: {query}\n"
            f"The query returned these results:\n{query_result}\n\n"
            "Please provide a clear, concise natural-language summary of "
            "these results that directly answers the user's question."
        )

        messages = build_chat_messages(
            system_prompt=system_prompt,
            conversation_history=session.get_llm_history(),
            user_message=context,
        )

        return self._llm.chat_completion(messages, temperature=0.3)
