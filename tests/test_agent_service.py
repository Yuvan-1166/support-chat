"""Tests for the agent service (LangGraph loop) and agent toolkit.

These tests are offline — no LLM calls or DB connections are made.
The LLM and session store are fully mocked.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.agent_tools import AgentToolkit, ToolResult
from app.services.agent_service import AgentService, AgentResponse, AgentState, AgentStepInfo


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_session(
    session_id: str = "test-session-001",
    query_type: str = "mysql",
    has_db: bool = False,
) -> Any:
    """Build a real Session object (no DB connection needed)."""
    from app.services.session_store import Session as DomainSession
    from app.schemas.session import QueryType, SchemaTable, SchemaField

    table = SchemaTable(
        name="contacts",
        description="Customer contacts",
        fields=[SchemaField(name="id", type="INT", is_primary_key=True)],
    )
    db_url = "mysql://user:pass@host/db" if has_db else None
    session = DomainSession(
        query_type=QueryType(query_type),
        schema_context=[table],
        db_url=db_url,
        system_instructions=None,
    )
    # Override auto-generated ID so tests can reference it
    session.session_id = session_id
    return session


def _make_toolkit() -> tuple[AgentToolkit, MagicMock, MagicMock]:
    """Return (toolkit, mock_store, mock_translator)."""
    store = MagicMock()
    translator = MagicMock()
    toolkit = AgentToolkit(store, translator)
    return toolkit, store, translator


# ─────────────────────────────────────────────────────────────────────────────
# AgentToolkit — registry
# ─────────────────────────────────────────────────────────────────────────────

class TestAgentToolkitRegistry:
    def test_all_six_tools_registered(self):
        toolkit, _, _ = _make_toolkit()
        tools = toolkit.get_tools()
        assert set(tools.keys()) == {
            "execute_query",
            "search_schema",
            "get_context",
            "create_task",
            "update_contact",
            "send_email",
        }

    def test_unknown_tool_returns_failure(self):
        toolkit, _, _ = _make_toolkit()
        result = toolkit.call_tool(_make_session(), "nonexistent_tool", {})
        assert result.success is False
        assert "Unknown tool" in result.error
        assert "nonexistent_tool" in result.error

    def test_tool_exception_is_caught(self):
        toolkit, _, _ = _make_toolkit()
        # Force the search_schema tool to raise unexpectedly
        toolkit._tools["search_schema"] = MagicMock(side_effect=RuntimeError("boom"))
        result = toolkit.call_tool(_make_session(), "search_schema", {})
        assert result.success is False
        assert "boom" in result.error


# ─────────────────────────────────────────────────────────────────────────────
# Tool: search_schema
# ─────────────────────────────────────────────────────────────────────────────

class TestSearchSchemaTool:
    def test_returns_all_tables_without_filter(self):
        toolkit, _, _ = _make_toolkit()
        session = _make_session()
        result = toolkit.call_tool(session, "search_schema", {})
        assert result.success is True
        assert result.data["total_tables"] == 1
        assert result.data["matching_tables"][0]["name"] == "contacts"

    def test_filter_by_matching_term(self):
        toolkit, _, _ = _make_toolkit()
        session = _make_session()
        result = toolkit.call_tool(session, "search_schema", {"search_term": "conta"})
        assert result.success is True
        assert len(result.data["matching_tables"]) == 1

    def test_filter_by_non_matching_term(self):
        toolkit, _, _ = _make_toolkit()
        session = _make_session()
        result = toolkit.call_tool(session, "search_schema", {"search_term": "invoices"})
        assert result.success is True
        assert result.data["matching_tables"] == []


# ─────────────────────────────────────────────────────────────────────────────
# Tool: get_context
# ─────────────────────────────────────────────────────────────────────────────

class TestGetContextTool:
    def test_returns_session_metadata(self):
        toolkit, _, _ = _make_toolkit()
        session = _make_session()
        session.messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        result = toolkit.call_tool(session, "get_context", {"limit": 10})
        assert result.success is True
        assert result.data["query_type"] == "mysql"
        assert result.data["message_count"] == 2

    def test_limit_respected(self):
        toolkit, _, _ = _make_toolkit()
        session = _make_session()
        session.messages = [{"role": "user", "content": str(i)} for i in range(20)]
        result = toolkit.call_tool(session, "get_context", {"limit": 3})
        assert len(result.data["recent_messages"]) == 3


# ─────────────────────────────────────────────────────────────────────────────
# Tool: create_task
# ─────────────────────────────────────────────────────────────────────────────

class TestCreateTaskTool:
    def test_creates_task_with_title(self):
        toolkit, _, _ = _make_toolkit()
        session = _make_session()
        result = toolkit.call_tool(session, "create_task", {"title": "Follow up with Alice"})
        assert result.success is True
        assert result.data["title"] == "Follow up with Alice"
        assert result.data["status"] == "pending"
        assert "task_id" in result.data

    def test_missing_title_returns_failure(self):
        toolkit, _, _ = _make_toolkit()
        result = toolkit.call_tool(_make_session(), "create_task", {})
        assert result.success is False
        assert "'title' is required" in result.error

    def test_optional_fields_included(self):
        toolkit, _, _ = _make_toolkit()
        result = toolkit.call_tool(
            _make_session(),
            "create_task",
            {"title": "T", "description": "desc", "priority": "high"},
        )
        assert result.success is True
        assert result.data["priority"] == "high"
        assert result.data["description"] == "desc"


# ─────────────────────────────────────────────────────────────────────────────
# Tool: update_contact
# ─────────────────────────────────────────────────────────────────────────────

class TestUpdateContactTool:
    def test_updates_contact_successfully(self):
        toolkit, _, _ = _make_toolkit()
        result = toolkit.call_tool(
            _make_session(),
            "update_contact",
            {"contact_id": "c42", "fields": {"status": "customer"}},
        )
        assert result.success is True
        assert result.data["contact_id"] == "c42"
        assert result.data["updated_fields"]["status"] == "customer"

    def test_missing_contact_id_fails(self):
        toolkit, _, _ = _make_toolkit()
        result = toolkit.call_tool(
            _make_session(), "update_contact", {"fields": {"status": "lead"}}
        )
        assert result.success is False

    def test_missing_fields_fails(self):
        toolkit, _, _ = _make_toolkit()
        result = toolkit.call_tool(
            _make_session(), "update_contact", {"contact_id": "c1"}
        )
        assert result.success is False


# ─────────────────────────────────────────────────────────────────────────────
# Tool: send_email
# ─────────────────────────────────────────────────────────────────────────────

class TestSendEmailTool:
    def test_sends_email_successfully(self):
        toolkit, _, _ = _make_toolkit()
        result = toolkit.call_tool(
            _make_session(),
            "send_email",
            {"to": "alice@example.com", "subject": "Hello", "body": "Hi there"},
        )
        assert result.success is True
        assert result.data["to"] == "alice@example.com"
        assert result.data["status"] == "sent"

    def test_missing_required_fields_fails(self):
        toolkit, _, _ = _make_toolkit()
        result = toolkit.call_tool(
            _make_session(), "send_email", {"to": "alice@example.com"}
        )
        assert result.success is False
        assert "required" in result.error


# ─────────────────────────────────────────────────────────────────────────────
# Tool: execute_query (mocked translator)
# ─────────────────────────────────────────────────────────────────────────────

class TestExecuteQueryTool:
    def test_translate_only_returns_query(self):
        toolkit, _, translator = _make_toolkit()
        translation = MagicMock()
        translation.query = "SELECT COUNT(*) FROM contacts"
        translation.explanation = "Counts all contacts"
        translation.confidence = 0.95
        translator.translate.return_value = translation

        result = toolkit.call_tool(
            _make_session(),
            "execute_query",
            {"question": "How many contacts?", "translate_only": True},
        )
        assert result.success is True
        assert result.data["query"] == "SELECT COUNT(*) FROM contacts"
        assert result.data["explanation"] == "Counts all contacts"

    def test_missing_question_fails(self):
        toolkit, _, _ = _make_toolkit()
        result = toolkit.call_tool(_make_session(), "execute_query", {})
        assert result.success is False
        assert "'question' is required" in result.error

    def test_no_db_skips_execution(self):
        toolkit, _, translator = _make_toolkit()
        translation = MagicMock()
        translation.query = "SELECT 1"
        translation.explanation = "test"
        translation.confidence = 1.0
        translator.translate.return_value = translation

        session = _make_session(has_db=False)
        result = toolkit.call_tool(
            session, "execute_query", {"question": "test query"}
        )
        assert result.success is True
        assert "no db_url" in result.data.get("note", "").lower()


# ─────────────────────────────────────────────────────────────────────────────
# AgentState and AgentResponse models
# ─────────────────────────────────────────────────────────────────────────────

class TestAgentModels:
    def test_agent_state_defaults(self):
        session = _make_session()
        state = AgentState(user_message="hello", session=session)
        assert state.current_step == 0
        assert state.should_continue is True
        assert state.tool_results == []
        assert state.next_node == "think"

    def test_agent_response_defaults(self):
        resp = AgentResponse(content="done")
        assert resp.role == "assistant"
        assert resp.agent_reasoning == []
        assert resp.error is None

    def test_agent_step_info_fields(self):
        step = AgentStepInfo(
            step=1,
            node="execute_tool",
            tool_name="search_schema",
            action="Executed search_schema: success",
        )
        assert step.step == 1
        assert step.tool_name == "search_schema"


# ─────────────────────────────────────────────────────────────────────────────
# AgentService — run_agent with mocked LLM
# ─────────────────────────────────────────────────────────────────────────────

class TestAgentServiceRun:
    def _make_service(self, llm_responses: list[str]) -> AgentService:
        """Build an AgentService with a mock LLM that cycles through responses."""
        store = MagicMock()
        translator = MagicMock()

        # Mock translation result
        translation = MagicMock()
        translation.query = "SELECT COUNT(*) FROM contacts"
        translation.explanation = "Counts contacts"
        translation.confidence = 0.9
        translator.translate.return_value = translation

        with patch("app.services.agent_service.ChatGroq") as mock_groq:
            mock_llm = MagicMock()
            responses = iter(llm_responses)

            def side_effect(prompt):
                resp = MagicMock()
                resp.content = next(responses, '{"thought":"done","selected_tool":null,"tool_input":{},"is_complete":true}')
                return resp

            mock_llm.invoke.side_effect = side_effect
            mock_groq.return_value = mock_llm

            service = AgentService(store, translator)
            return service

    def test_agent_completes_with_no_tool(self):
        service = self._make_service([
            '{"thought":"Nothing to do","selected_tool":null,"tool_input":{},"is_complete":true}'
        ])
        session = _make_session()
        response = service.run_agent(session, "Hello")
        assert isinstance(response, AgentResponse)
        assert response.role == "assistant"
        assert response.content != ""

    def test_agent_calls_search_schema(self):
        service = self._make_service([
            '{"thought":"I should check the schema","selected_tool":"search_schema","tool_input":{"search_term":""},"is_complete":false}',
            '{"thought":"Done","selected_tool":null,"tool_input":{},"is_complete":true}',
        ])
        session = _make_session()
        response = service.run_agent(session, "What tables do I have?")
        assert isinstance(response, AgentResponse)
        assert len(response.final_tool_results) >= 1
        assert response.final_tool_results[0]["tool"] == "search_schema"
        assert response.final_tool_results[0]["success"] is True

    def test_agent_calls_create_task(self):
        service = self._make_service([
            '{"thought":"Create a task","selected_tool":"create_task","tool_input":{"title":"Call Alice"},"is_complete":false}',
            '{"thought":"Done","selected_tool":null,"tool_input":{},"is_complete":true}',
        ])
        session = _make_session()
        response = service.run_agent(session, "Create a task to call Alice")
        assert any(r["tool"] == "create_task" for r in response.final_tool_results)

    def test_agent_respects_max_steps(self):
        # Always wants to continue — should be cut off by max_steps=2
        service = self._make_service([
            '{"thought":"step","selected_tool":"search_schema","tool_input":{},"is_complete":false}',
            '{"thought":"step","selected_tool":"search_schema","tool_input":{},"is_complete":false}',
            '{"thought":"step","selected_tool":"search_schema","tool_input":{},"is_complete":false}',
        ])
        session = _make_session()
        response = service.run_agent(session, "loop forever", max_steps=2)
        assert isinstance(response, AgentResponse)
        assert len(response.final_tool_results) <= 2

    def test_agent_handles_malformed_llm_json(self):
        service = self._make_service(["not valid json at all"])
        session = _make_session()
        response = service.run_agent(session, "test")
        # Should fail gracefully, not raise
        assert isinstance(response, AgentResponse)

    def test_run_agent_async_returns_same_as_sync(self):
        service = self._make_service([
            '{"thought":"Nothing to do","selected_tool":null,"tool_input":{},"is_complete":true}'
        ])
        session = _make_session()
        sync_resp = service.run_agent(session, "ping")
        async_resp = asyncio.run(service.run_agent_async(session, "ping"))
        # Both should return AgentResponse
        assert isinstance(sync_resp, AgentResponse)
        assert isinstance(async_resp, AgentResponse)


# ─────────────────────────────────────────────────────────────────────────────
# MCP server — smoke test (no DB needed)
# ─────────────────────────────────────────────────────────────────────────────

class TestMCPServerCreation:
    def test_mcp_server_creates_without_error(self):
        from app.mcp.server import create_mcp_server
        store = MagicMock()
        translator = MagicMock()
        mcp = create_mcp_server(store, translator)
        assert mcp is not None
        assert mcp.name == "SupportChatAgent"

    def test_mcp_server_has_expected_tools(self):
        from app.mcp.server import create_mcp_server
        from mcp.server.fastmcp import FastMCP

        store = MagicMock()
        translator = MagicMock()
        mcp = create_mcp_server(store, translator)

        # FastMCP stores registered tools in _tool_manager
        tool_names = list(mcp._tool_manager._tools.keys())
        assert "execute_query" in tool_names
        assert "search_schema" in tool_names
        assert "get_context" in tool_names
        assert "create_task" in tool_names
        assert "update_contact" in tool_names
        assert "send_email" in tool_names
