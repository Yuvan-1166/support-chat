"""MCP Server for Support Chat.

Registers all agent tools and session resources via FastMCP decorators,
then exposes a helper to mount the SSE transport onto the FastAPI app.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP

from app.services.agent_tools import AgentToolkit
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
    toolkit = AgentToolkit(session_store, translator)
    mcp = FastMCP("SupportChatAgent")

    # ── Resources ────────────────────────────────────────────────────────

    @mcp.resource("session://{session_id}")
    def get_session_resource(session_id: str) -> str:
        """Returns the full context of a chat session as JSON.

        Includes query type, schema tables, DB connection status,
        system instructions, and recent message count.
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

    @mcp.resource("contacts://list")
    def get_contacts_resource() -> str:
        """Returns a placeholder list of CRM contacts as JSON.

        In a real deployment this would query the CRM API.
        """
        contacts = [
            {"id": "c1", "name": "Alice", "email": "alice@example.com", "status": "lead", "score": 10},
            {"id": "c2", "name": "Bob", "email": "bob@example.com", "status": "customer", "score": 100},
            {"id": "c3", "name": "Charlie", "email": "charlie@example.com", "status": "lead", "score": 25},
        ]
        return json.dumps(contacts)

    # ── Tools ─────────────────────────────────────────────────────────────

    @mcp.tool()
    def execute_query(session_id: str, question: str, translate_only: bool = False) -> str:
        """Translate a natural language question into a data query and optionally execute it.

        Returns JSON with keys: query, explanation, query_result, note, error.
        """
        session = session_store.get(session_id)
        if not session:
            return json.dumps({"error": f"Session '{session_id}' not found."})

        result = toolkit.call_tool(
            session,
            "execute_query",
            {"question": question, "translate_only": translate_only},
        )
        if not result.success:
            return json.dumps({"error": result.error or "Tool execution failed"})
        return json.dumps(result.data, default=str)

    @mcp.tool()
    def search_schema(session_id: str, search_term: str = "") -> str:
        """Inspect the schema context attached to a session.

        Optionally filter by a search term to find relevant tables or fields.
        Returns JSON with keys: tables, query_type, note.
        """
        session = session_store.get(session_id)
        if not session:
            return json.dumps({"error": f"Session '{session_id}' not found."})

        result = toolkit.call_tool(
            session,
            "search_schema",
            {"search_term": search_term},
        )
        if not result.success:
            return json.dumps({"error": result.error or "Tool execution failed"})
        return json.dumps(result.data, default=str)

    @mcp.tool()
    def get_context(session_id: str, last_n: int = 5) -> str:
        """Retrieve the recent conversation history and session metadata.

        Returns JSON with keys: session_id, query_type, message_count, recent_messages.
        """
        session = session_store.get(session_id)
        if not session:
            return json.dumps({"error": f"Session '{session_id}' not found."})

        result = toolkit.call_tool(
            session,
            "get_context",
            {"last_n": last_n},
        )
        if not result.success:
            return json.dumps({"error": result.error or "Tool execution failed"})
        return json.dumps(result.data, default=str)

    @mcp.tool()
    def create_task(
        session_id: str,
        title: str,
        description: str = "",
        priority: str = "normal",
    ) -> str:
        """Create a new task in the CRM.

        Returns JSON with keys: task_id, status, note, error.
        """
        session = session_store.get(session_id)
        if not session:
            return json.dumps({"error": f"Session '{session_id}' not found."})

        result = toolkit.call_tool(
            session,
            "create_task",
            {"title": title, "description": description, "priority": priority},
        )
        if not result.success:
            return json.dumps({"error": result.error or "Task creation failed"})
        return json.dumps(result.data, default=str)

    @mcp.tool()
    def update_contact(session_id: str, contact_id: str, fields: str) -> str:
        """Update fields on a CRM contact.

        `fields` should be a JSON string of key-value pairs to update.
        Returns JSON with keys: contact_id, status, note, error.
        """
        session = session_store.get(session_id)
        if not session:
            return json.dumps({"error": f"Session '{session_id}' not found."})

        try:
            fields_dict = json.loads(fields)
        except (json.JSONDecodeError, TypeError):
            return json.dumps({"error": "Invalid fields JSON."})

        result = toolkit.call_tool(
            session,
            "update_contact",
            {"contact_id": contact_id, "fields": fields_dict},
        )
        if not result.success:
            return json.dumps({"error": result.error or "Contact update failed"})
        return json.dumps(result.data, default=str)

    @mcp.tool()
    def send_email(session_id: str, to: str, subject: str, body: str) -> str:
        """Send an email through the CRM.

        Returns JSON with keys: message_id, status, note, error.
        """
        session = session_store.get(session_id)
        if not session:
            return json.dumps({"error": f"Session '{session_id}' not found."})

        result = toolkit.call_tool(
            session,
            "send_email",
            {"to": to, "subject": subject, "body": body},
        )
        if not result.success:
            return json.dumps({"error": result.error or "Email send failed"})
        return json.dumps(result.data, default=str)

    logger.info("MCP server 'SupportChatAgent' created with %d tools and 2 resources.", 6)
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
