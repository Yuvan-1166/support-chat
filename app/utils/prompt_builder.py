"""Prompt construction utilities for the query-translation LLM."""

from __future__ import annotations

from app.schemas.session import QueryType, SchemaTable


def _format_schema(tables: list[SchemaTable]) -> str:
    """Render schema tables as a human-readable text block for the LLM."""
    parts: list[str] = []
    for table in tables:
        fields = ", ".join(
            f"{f.name} ({f.type}{'  PK' if f.is_primary_key else ''})"
            for f in table.fields
        )
        desc = f" — {table.description}" if table.description else ""
        parts.append(f"  • {table.name}{desc}\n    Fields: {fields}")
    return "\n".join(parts)


_QUERY_DIALECT_HINTS: dict[QueryType, str] = {
    QueryType.SQL: "Standard SQL (ANSI)",
    QueryType.MYSQL: "MySQL dialect",
    QueryType.POSTGRESQL: "PostgreSQL dialect",
    QueryType.SQLITE: "SQLite dialect",
    QueryType.MONGODB: "MongoDB query (JSON format using find/aggregate syntax)",
    QueryType.PANDAS: "Python Pandas expression (e.g. df.query() or df[df['col'] > val])",
}


def build_system_prompt(
    query_type: QueryType,
    schema_context: list[SchemaTable],
    system_instructions: str | None = None,
) -> str:
    """Build the LLM system prompt with schema context and instructions."""
    dialect = _QUERY_DIALECT_HINTS.get(query_type, str(query_type.value))
    schema_text = _format_schema(schema_context)

    prompt = (
        "You are a helpful data assistant. Your job is to translate the user's "
        "natural-language questions into data queries and, when provided with "
        "query results, explain the data in plain English.\n\n"
        f"TARGET QUERY LANGUAGE: {dialect}\n\n"
        "DATABASE SCHEMA:\n"
        f"{schema_text}\n\n"
        "RULES:\n"
        "1. When the user asks a data question, respond with a JSON object:\n"
        '   {"query": "<the generated query>", "explanation": "<brief explanation>", '
        '"confidence": <0.0-1.0>}\n'
        "2. When the user provides query results or asks follow-up questions "
        "about data, respond in natural language.\n"
        "3. Never generate queries that modify data (INSERT, UPDATE, DELETE, DROP, etc.).\n"
        "4. If you cannot generate a valid query, explain why in the 'explanation' field "
        "and set confidence to 0.\n"
        "5. Keep queries efficient and well-formatted.\n"
    )

    if system_instructions:
        prompt += f"\nADDITIONAL INSTRUCTIONS:\n{system_instructions}\n"

    return prompt


def build_chat_messages(
    system_prompt: str,
    conversation_history: list[dict[str, str]],
    user_message: str,
) -> list[dict[str, str]]:
    """Assemble the full message list ready for the LLM API call.

    Returns
    -------
    list[dict]
        ``[{"role": "system", ...}, *history, {"role": "user", ...}]``
    """
    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    messages.extend(conversation_history)
    messages.append({"role": "user", "content": user_message})
    return messages
