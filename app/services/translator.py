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


def _format_result_as_table(query_result: Any) -> str:
    """Convert query results into a Markdown table for clearer LLM interpretation.

    Falls back to a plain repr for non-tabular data.
    """
    if not isinstance(query_result, list) or not query_result:
        return str(query_result)

    first_row = query_result[0]
    if not isinstance(first_row, dict):
        return str(query_result)

    headers = list(first_row.keys())
    rows = [headers]
    for row in query_result[:50]:  # Limit to first 50 rows for LLM performance
        rows.append([str(row.get(h, "")) for h in headers])

    # Build Markdown table
    col_widths = [max(len(str(r[i])) for r in rows) for i in range(len(headers))]
    sep = "| " + " | ".join("-" * w for w in col_widths) + " |"
    lines: list[str] = []
    for i, row in enumerate(rows):
        line = "| " + " | ".join(str(cell).ljust(col_widths[j]) for j, cell in enumerate(row)) + " |"
        lines.append(line)
        if i == 0:
            lines.append(sep)

    row_count = len(query_result)
    lines.append(f"\n({row_count} row{'s' if row_count != 1 else ''} returned)")
    return "\n".join(lines)


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

        formatted_result = _format_result_as_table(query_result)

        # Build a rich context message that frames the data clearly for the LLM
        context = (
            f"The user asked: \"{user_message}\"\n\n"
            f"The executed query was:\n{query}\n\n"
            f"The query returned the following results:\n{formatted_result}\n\n"
            "Your task:\n"
            "- Provide a clear, direct natural-language answer to the user's question "
            "using the data above.\n"
            "- Present key values (names, amounts, counts) explicitly — do NOT just "
            "say 'see the table above'.\n"
            "- Format monetary values with currency symbols and commas "
            "(e.g. $6,400.00).\n"
            "- If the result contains only numeric IDs instead of names or labels, "
            "acknowledge this limitation and suggest the user re-run with a query "
            "that JOINs the appropriate reference table.\n"
            "- If the result is empty, say so clearly and suggest possible reasons.\n"
            "- Be concise: 2–5 sentences unless the data demands more detail.\n"
        )

        messages = build_chat_messages(
            system_prompt=system_prompt,
            conversation_history=session.get_llm_history(),
            user_message=context,
        )

        return self._llm.chat_completion(messages, temperature=0.3)
