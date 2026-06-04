"""Tool definitions for agent-mode operations.

These tools represent actions the agent can take:
- execute_query: translate and run a data query
- create_task: create a task in the CRM
- update_contact: update a contact in the CRM
- send_email: send an email through the CRM
- search_schema: introspect the current schema
- get_conversation_context: retrieve relevant history
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional

from app.services.adapters import get_adapter
from app.services.session_store import Session, SessionStoreBase
from app.services.translator import QueryTranslator
from app.utils.json_safety import make_json_safe

logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    """Uniform result container for all tool executions."""

    tool_name: str
    success: bool
    data: Any = None
    error: Optional[str] = None


class AgentToolkit:
    """Centralized registry and executor for agent tools.
    
    Each tool is a callable that takes session, session_store, and kwargs,
    then returns a ToolResult.
    """

    def __init__(
        self,
        session_store: SessionStoreBase,
        translator: QueryTranslator,
    ) -> None:
        self.session_store = session_store
        self.translator = translator
        self._tools: dict[str, Callable] = {
            "execute_query": self._execute_query_tool,
            "search_schema": self._search_schema_tool,
            "get_context": self._get_context_tool,
            "create_task": self._create_task_tool,
            "update_contact": self._update_contact_tool,
            "send_email": self._send_email_tool,
        }

    def get_tools(self) -> dict[str, Callable]:
        """Return all available tools."""
        return self._tools.copy()

    def call_tool(
        self,
        session: Session,
        tool_name: str,
        tool_input: dict[str, Any],
    ) -> ToolResult:
        """Call a specific tool by name."""
        if tool_name not in self._tools:
            return ToolResult(
                tool_name=tool_name,
                success=False,
                error=f"Unknown tool: {tool_name}. Available: {', '.join(self._tools.keys())}",
            )

        try:
            tool_fn = self._tools[tool_name]
            result = tool_fn(session, tool_input)
            return result
        except Exception as exc:
            logger.exception(f"Tool execution failed for {tool_name}")
            return ToolResult(
                tool_name=tool_name,
                success=False,
                error=str(exc),
            )

    # ─────────────────────────────────────────────────────────────────
    # Tool Implementations
    # ─────────────────────────────────────────────────────────────────

    def _execute_query_tool(
        self,
        session: Session,
        tool_input: dict[str, Any],
    ) -> ToolResult:
        """Execute a data query or translate a natural language question.
        
        Args:
            session: Current session
            tool_input: {
                "question": str (required),
                "translate_only": bool (optional, default False)
            }
        
        Returns:
            ToolResult with query and results
        """
        question = tool_input.get("question")
        if not question:
            return ToolResult(
                tool_name="execute_query",
                success=False,
                error="'question' is required",
            )

        translate_only = tool_input.get("translate_only", False)

        try:
            # Translate the question
            translation_result = self.translator.translate(session, question)
            query = translation_result.query

            if not query:
                return ToolResult(
                    tool_name="execute_query",
                    success=False,
                    error=translation_result.raw_response.get("error", "No query generated"),
                )

            data = {
                "query": query,
                "explanation": translation_result.explanation,
                "confidence": translation_result.confidence,
            }

            if translate_only:
                return ToolResult(
                    tool_name="execute_query",
                    success=True,
                    data=data,
                )

            # Execute if session has db connection
            if not session.has_db_connection:
                data["note"] = "Session has no db_url; only translation available"
                return ToolResult(
                    tool_name="execute_query",
                    success=True,
                    data=data,
                )

            adapter = None
            try:
                adapter = get_adapter(session.query_type, session.db_url)
                if adapter is not None:
                    query_result = adapter.execute(query)
                    data["query_result"] = make_json_safe(query_result)
            finally:
                if adapter is not None:
                    try:
                        adapter.close()
                    except Exception:
                        logger.exception("Failed to close adapter")

            return ToolResult(
                tool_name="execute_query",
                success=True,
                data=data,
            )

        except Exception as exc:
            return ToolResult(
                tool_name="execute_query",
                success=False,
                error=str(exc),
            )

    def _search_schema_tool(
        self,
        session: Session,
        tool_input: dict[str, Any],
    ) -> ToolResult:
        """Search or display current schema context.
        
        Args:
            session: Current session
            tool_input: {
                "search_term": str (optional)
            }
        
        Returns:
            ToolResult with matching schema tables
        """
        search_term = tool_input.get("search_term", "").lower()
        
        matching_tables = []
        for table in session.schema_context:
            if not search_term or search_term in table.name.lower():
                matching_tables.append({
                    "name": table.name,
                    "description": table.description,
                    "fields": [
                        {
                            "name": f.name,
                            "type": f.type,
                            "is_primary_key": f.is_primary_key,
                        }
                        for f in table.fields
                    ],
                })

        return ToolResult(
            tool_name="search_schema",
            success=True,
            data={
                "total_tables": len(session.schema_context),
                "matching_tables": matching_tables,
                "search_term": search_term or "(none)",
            },
        )

    def _get_context_tool(
        self,
        session: Session,
        tool_input: dict[str, Any],
    ) -> ToolResult:
        """Retrieve conversation context (recent messages, system instructions).
        
        Args:
            session: Current session
            tool_input: {
                "limit": int (optional, default 10)
            }
        
        Returns:
            ToolResult with messages and metadata
        """
        limit = tool_input.get("limit", 10)
        
        recent_messages = session.messages[-limit:]
        return ToolResult(
            tool_name="get_context",
            success=True,
            data={
                "query_type": session.query_type,
                "system_instructions": session.system_instructions,
                "has_db_connection": session.has_db_connection,
                "recent_messages": recent_messages,
                "message_count": len(session.messages),
            },
        )

    def _create_task_tool(
        self,
        session: Session,
        tool_input: dict[str, Any],
    ) -> ToolResult:
        """Create a task in the CRM (stub — would call CRM API).
        
        Args:
            session: Current session
            tool_input: {
                "title": str (required),
                "description": str (optional),
                "assigned_to": str (optional),
                "priority": str (optional, default "normal")
            }
        
        Returns:
            ToolResult with task_id
        """
        title = tool_input.get("title")
        if not title:
            return ToolResult(
                tool_name="create_task",
                success=False,
                error="'title' is required",
            )

        # TODO: Integrate with CRM API (POST /api/tasks or similar)
        # For now, return a mock success
        logger.info(f"[STUB] Creating task: {title}")
        
        return ToolResult(
            tool_name="create_task",
            success=True,
            data={
                "task_id": "task_stub_123",
                "title": title,
                "description": tool_input.get("description"),
                "assigned_to": tool_input.get("assigned_to"),
                "priority": tool_input.get("priority", "normal"),
                "status": "pending",
                "note": "Task creation is stubbed; integrate with CRM API",
            },
        )

    def _update_contact_tool(
        self,
        session: Session,
        tool_input: dict[str, Any],
    ) -> ToolResult:
        """Update a contact in the CRM (stub — would call CRM API).
        
        Args:
            session: Current session
            tool_input: {
                "contact_id": str (required),
                "fields": dict (required, e.g. {"name": "Jane", "status": "customer"})
            }
        
        Returns:
            ToolResult with update confirmation
        """
        contact_id = tool_input.get("contact_id")
        fields = tool_input.get("fields")
        
        if not contact_id or not fields:
            return ToolResult(
                tool_name="update_contact",
                success=False,
                error="'contact_id' and 'fields' are required",
            )

        # TODO: Integrate with CRM API (PATCH /api/contacts/:id or similar)
        logger.info(f"[STUB] Updating contact {contact_id} with {fields}")
        
        return ToolResult(
            tool_name="update_contact",
            success=True,
            data={
                "contact_id": contact_id,
                "updated_fields": fields,
                "note": "Contact update is stubbed; integrate with CRM API",
            },
        )

    def _send_email_tool(
        self,
        session: Session,
        tool_input: dict[str, Any],
    ) -> ToolResult:
        """Send an email through the CRM (stub — would call CRM API).
        
        Args:
            session: Current session
            tool_input: {
                "to": str (required),
                "subject": str (required),
                "body": str (required),
                "cc": str (optional),
                "bcc": str (optional)
            }
        
        Returns:
            ToolResult with email_id
        """
        to = tool_input.get("to")
        subject = tool_input.get("subject")
        body = tool_input.get("body")
        
        if not all([to, subject, body]):
            return ToolResult(
                tool_name="send_email",
                success=False,
                error="'to', 'subject', and 'body' are required",
            )

        # TODO: Integrate with CRM API (POST /api/emails or similar)
        logger.info(f"[STUB] Sending email to {to} with subject '{subject}'")
        
        return ToolResult(
            tool_name="send_email",
            success=True,
            data={
                "email_id": "email_stub_456",
                "to": to,
                "subject": subject,
                "cc": tool_input.get("cc"),
                "bcc": tool_input.get("bcc"),
                "status": "sent",
                "note": "Email sending is stubbed; integrate with CRM API",
            },
        )
