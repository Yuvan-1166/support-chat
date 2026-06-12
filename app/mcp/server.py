"""MCP Server for Support Chat.

Exposes a small set of *read-only / knowledge* capabilities over the Model
Context Protocol (SSE transport) so external MCP clients (e.g. Claude) can
introspect sessions and query the ASK-mode knowledge base.

AGENT-mode CRM actions are intentionally NOT exposed here: they require the
per-employee JWT forwarded by the CRM proxy (for auth + tenant scoping), which
is not available over the MCP SSE transport.  Use the REST ``/sessions/{id}/chat``
endpoint with ``mode=agent`` for actions.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP

from app.core.llm import get_llm_client
from app.rag.store import get_knowledge_store
from app.services.session_store import SessionStoreBase
from app.services.translator import QueryTranslator

logger = logging.getLogger(__name__)

# Module-level singleton — created once during app startup.
_mcp_server: Optional[FastMCP] = None


def get_mcp_server() -> Optional[FastMCP]:
    """Return the singleton MCP server, or None if not yet initialised."""
    return _mcp_server


def create_mcp_server(
    session_store: SessionStoreBase,
    translator: QueryTranslator,
) -> FastMCP:
    """Create, configure, and return the FastMCP server instance."""
    mcp = FastMCP("SupportChatAgent")

    # ── Resources ────────────────────────────────────────────────────────

    @mcp.resource("session://{session_id}")
    def get_session_resource(session_id: str) -> str:
        """Returns the full context of a chat session as JSON.

        Includes query type, schema tables, DB connection status,
        system instructions, and message count.
        """
        session = session_store.get(session_id)
        if not session:
            return json.dumps({"error": f"Session '{session_id}' not found."})

        context = {
            "session_id": session.session_id,
            "query_type": session.query_type,
            "has_db_connection": session.has_db_connection,
            "system_instructions": session.system_instructions,
            "message_count": len(session.messages),
            "schema_context": [
                {
                    "name": t.name,
                    "description": t.description,
                    "fields": [f.model_dump() for f in t.fields],
                }
                for t in session.schema_context
            ],
        }
        return json.dumps(context, default=str)

    # ── Tools ─────────────────────────────────────────────────────────────

    @mcp.tool()
    def ask_knowledge(question: str, top_k: int = 5) -> str:
        """Answer a how-to / navigation question from the CRM knowledge base.

        Retrieves the most relevant indexed documentation chunks and asks the
        LLM to answer grounded on them.  Returns JSON with keys: answer, sources.
        """
        store = get_knowledge_store()
        snippets = store.retrieve(question, k=top_k)
        if not snippets:
            return json.dumps(
                {
                    "answer": "No knowledge has been indexed yet. Run the RAG "
                    "ingestion (python -m app.rag.ingest) first.",
                    "sources": [],
                }
            )

        context = "\n\n---\n\n".join(
            f"[source: {s['metadata'].get('source', '?')}]\n{s['text']}"
            for s in snippets
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "Answer the question about how the CRM works using ONLY the "
                    "knowledge snippets. Do not invent steps or menu names. If the "
                    "snippets don't contain the answer, say so."
                ),
            },
            {
                "role": "user",
                "content": f"KNOWLEDGE SNIPPETS:\n{context}\n\nQUESTION: {question}",
            },
        ]
        answer = get_llm_client().chat_completion(messages, temperature=0.2)
        return json.dumps(
            {
                "answer": answer,
                "sources": [s["metadata"].get("source") for s in snippets],
            },
            default=str,
        )

    @mcp.tool()
    def search_schema(session_id: str, search_term: str = "") -> str:
        """Inspect the schema context attached to a session.

        Optionally filter by a search term to find relevant tables.
        Returns JSON with keys: total_tables, matching_tables.
        """
        session = session_store.get(session_id)
        if not session:
            return json.dumps({"error": f"Session '{session_id}' not found."})

        term = (search_term or "").lower()
        matching = [
            {
                "name": t.name,
                "description": t.description,
                "fields": [
                    {"name": f.name, "type": f.type, "is_primary_key": f.is_primary_key}
                    for f in t.fields
                ],
            }
            for t in session.schema_context
            if not term or term in t.name.lower()
        ]
        return json.dumps(
            {"total_tables": len(session.schema_context), "matching_tables": matching},
            default=str,
        )

    @mcp.tool()
    def get_context(session_id: str, last_n: int = 5) -> str:
        """Retrieve recent conversation history and session metadata.

        Returns JSON with keys: query_type, has_db_connection, recent_messages,
        message_count.
        """
        session = session_store.get(session_id)
        if not session:
            return json.dumps({"error": f"Session '{session_id}' not found."})

        return json.dumps(
            {
                "query_type": session.query_type,
                "system_instructions": session.system_instructions,
                "has_db_connection": session.has_db_connection,
                "recent_messages": session.messages[-last_n:],
                "message_count": len(session.messages),
            },
            default=str,
        )

    logger.info("MCP server 'SupportChatAgent' created with 3 tools and 1 resource.")
    return mcp


def mount_mcp_server(
    app: FastAPI,
    session_store: SessionStoreBase,
    translator: QueryTranslator,
) -> FastMCP:
    """Create the MCP server and mount its SSE transport at /mcp.

    Returns the FastMCP instance so callers can reference it if needed.
    """
    global _mcp_server
    _mcp_server = create_mcp_server(session_store, translator)
    app.mount("/mcp", _mcp_server.sse_app())
    logger.info("MCP server mounted at /mcp")
    return _mcp_server
