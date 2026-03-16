"""Prompt construction utilities for the query-translation LLM."""

from __future__ import annotations

from app.schemas.session import QueryType, SchemaTable


def _format_schema(tables: list[SchemaTable]) -> str:
    """Render schema tables as a human-readable text block for the LLM.

    Each field shows: name (type[, PK][, FK→table.column]).
    FK relationships are critical — they tell the LLM which ID columns can
    be JOINed to get human-readable labels.
    """
    parts: list[str] = []
    for table in tables:
        field_parts: list[str] = []
        for f in table.fields:
            tags: list[str] = [f.type]
            if f.is_primary_key:
                tags.append("PK")
            if f.foreign_key:
                tags.append(f"FK→{f.foreign_key}")
            if f.description:
                tags.append(f.description)
            field_parts.append(f"{f.name} ({', '.join(tags)})")
        fields_text = ", ".join(field_parts)
        desc = f" — {table.description}" if table.description else ""
        parts.append(f"  • {table.name}{desc}\n    Fields: {fields_text}")
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
        "1. When the user asks a data question, respond with ONLY a JSON object:\n"
        '   {"query": "<the generated query>", "explanation": "<brief explanation>", '
        '"confidence": <0.0-1.0>}\n'
        "2. When the user provides query results or asks follow-up questions "
        "about data, respond in natural language.\n"
        "3. Never generate queries that modify data (INSERT, UPDATE, DELETE, DROP, etc.).\n"
        "4. If you cannot generate a valid query, explain why in the 'explanation' field "
        "and set confidence to 0.\n"
        "5. Keep queries efficient and well-formatted.\n"
        "6. ALWAYS SELECT human-readable columns (name, title, label, email, description) "
        "instead of bare numeric IDs. When a column is marked FK→table.column in the "
        "schema, JOIN that referenced table and SELECT its descriptive column (e.g. name, "
        "title) instead of the raw ID.\n"
        "7. Give EVERY aggregate expression a clear alias "
        "(e.g. COUNT(*) AS total_count, SUM(amount) AS total_amount).\n"
        "8. For 'top N', 'highest', 'most', 'best', or ranking questions, ALWAYS include "
        "ORDER BY <metric> DESC LIMIT N.\n"
        "9. Use COALESCE(column, 'N/A') for any displayed text column that could be NULL.\n"
        "10. Never return a result set that contains only ID columns when the schema has "
        "corresponding name/label columns accessible via a JOIN.\n"
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
