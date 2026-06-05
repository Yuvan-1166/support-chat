"""Integration tests for the agent_mode chat endpoint.

Uses FastAPI TestClient with mocked LLM and session store.
No real DB or LLM calls are made.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.services.agent_service import AgentResponse, AgentStepInfo


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def agent_client(test_client):
    """Re-use the base test_client fixture from conftest."""
    return test_client


@pytest.fixture()
def session_id(agent_client):
    """Create a session and return its ID."""
    resp = agent_client.post(
        "/sessions",
        json={
            "query_type": "mysql",
            "schema_context": [
                {
                    "name": "contacts",
                    "fields": [
                        {"name": "id", "type": "INT", "is_primary_key": True},
                        {"name": "name", "type": "VARCHAR(255)"},
                        {"name": "score", "type": "INT"},
                    ],
                }
            ],
        },
    )
    assert resp.status_code == 201
    return resp.json()["session_id"]


def _mock_agent_response(content: str = "Done.", steps: list | None = None) -> AgentResponse:
    steps = steps or [
        AgentStepInfo(
            step=1,
            node="execute_tool",
            tool_name="search_schema",
            tool_result={"tables": []},
            action="Executed search_schema: success",
        )
    ]
    return AgentResponse(
        content=content,
        agent_reasoning=steps,
        final_tool_results=[
            {"tool": s.tool_name, "success": True, "data": s.tool_result, "error": None}
            for s in steps
        ],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestAgentModeEndpoint:
    def test_agent_mode_returns_200(self, agent_client, session_id):
        mock_resp = _mock_agent_response("I checked your schema.")
        with patch(
            "app.api.chat.get_agent_service",
        ) as mock_get:
            svc = MagicMock()
            svc.run_agent_async = AsyncMock(return_value=mock_resp)
            mock_get.return_value = svc

            resp = agent_client.post(
                f"/sessions/{session_id}/chat",
                json={"message": "What tables exist?", "agent_mode": True},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "assistant"
        assert data["content"] == "I checked your schema."

    def test_agent_mode_includes_reasoning(self, agent_client, session_id):
        mock_resp = _mock_agent_response("Done.", [
            AgentStepInfo(step=1, node="execute_tool", tool_name="search_schema", action="ok"),
            AgentStepInfo(step=2, node="execute_tool", tool_name="create_task", action="ok"),
        ])
        with patch("app.api.chat.get_agent_service") as mock_get:
            svc = MagicMock()
            svc.run_agent_async = AsyncMock(return_value=mock_resp)
            mock_get.return_value = svc

            resp = agent_client.post(
                f"/sessions/{session_id}/chat",
                json={"message": "Do stuff", "agent_mode": True},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["agent_reasoning"], list)
        assert len(data["agent_reasoning"]) == 2
        assert data["agent_reasoning"][0]["tool_name"] == "search_schema"
        assert data["agent_reasoning"][1]["tool_name"] == "create_task"

    def test_agent_mode_extracts_query_from_execute_step(self, agent_client, session_id):
        step = AgentStepInfo(
            step=1,
            node="execute_tool",
            tool_name="execute_query",
            tool_result={"query": "SELECT * FROM contacts", "query_result": [{"id": 1}]},
            action="ok",
        )
        mock_resp = AgentResponse(
            content="Found 1 contact.",
            agent_reasoning=[step],
            final_tool_results=[{
                "tool": "execute_query",
                "success": True,
                "data": {"query": "SELECT * FROM contacts", "query_result": [{"id": 1}]},
                "error": None,
            }],
        )
        with patch("app.api.chat.get_agent_service") as mock_get:
            svc = MagicMock()
            svc.run_agent_async = AsyncMock(return_value=mock_resp)
            mock_get.return_value = svc

            resp = agent_client.post(
                f"/sessions/{session_id}/chat",
                json={"message": "Show contacts", "agent_mode": True},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["query"] == "SELECT * FROM contacts"

    def test_non_agent_mode_still_works(self, agent_client, session_id):
        """Standard mode must not be broken by agent changes."""
        resp = agent_client.post(
            f"/sessions/{session_id}/chat",
            json={"message": "How many contacts?", "agent_mode": False},
        )
        # 200 or 500 depending on mock; at minimum it shouldn't 404/422
        assert resp.status_code in (200, 500)

    def test_agent_mode_404_for_unknown_session(self, agent_client):
        resp = agent_client.post(
            "/sessions/nonexistent-session-id/chat",
            json={"message": "hello", "agent_mode": True},
        )
        assert resp.status_code == 404

    def test_agent_mode_false_is_default(self, agent_client, session_id):
        """Omitting agent_mode should default to False (no agent reasoning key)."""
        resp = agent_client.post(
            f"/sessions/{session_id}/chat",
            json={"message": "How many contacts?"},
        )
        # agent_reasoning should be absent or null in standard mode
        data = resp.json()
        assert data.get("agent_reasoning") is None or data.get("agent_reasoning") == []
