"""Tests for the chat endpoint."""

from __future__ import annotations


def _create_session(test_client, **overrides):
    """Helper to create a session with default payload."""
    payload = {
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
    }
    payload.update(overrides)
    resp = test_client.post("/sessions", json=payload)
    assert resp.status_code == 201
    return resp.json()["session_id"]


class TestSendMessage:
    def test_returns_generated_query(self, test_client):
        session_id = _create_session(test_client)

        resp = test_client.post(
            f"/sessions/{session_id}/chat",
            json={"message": "How many contacts have a score above 5?"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "assistant"
        assert data["query"] is not None
        assert "SELECT" in data["query"]

    def test_returns_404_for_unknown_session(self, test_client):
        resp = test_client.post(
            "/sessions/nonexistent/chat",
            json={"message": "Hello"},
        )
        assert resp.status_code == 404

    def test_conversation_history_grows(self, test_client):
        session_id = _create_session(test_client)

        # First message
        test_client.post(
            f"/sessions/{session_id}/chat",
            json={"message": "How many contacts?"},
        )

        # Second message
        test_client.post(
            f"/sessions/{session_id}/chat",
            json={"message": "What about score above 10?"},
        )

        # Check history
        resp = test_client.get(f"/sessions/{session_id}/history")
        assert resp.status_code == 200
        messages = resp.json()["messages"]
        # 2 user messages + 2 assistant replies = 4
        assert len(messages) == 4

    def test_query_result_triggers_insight(self, test_client, mock_llm_client):
        session_id = _create_session(test_client)

        resp = test_client.post(
            f"/sessions/{session_id}/chat",
            json={
                "message": "Explain these results",
                "query_result": [{"count": 42}],
                "generate_insight": True,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        # The mock returns a fixed insight string
        assert "42" in data["content"]

    def test_no_execution_without_db_url(self, test_client):
        session_id = _create_session(test_client)  # no db_url

        resp = test_client.post(
            f"/sessions/{session_id}/chat",
            json={
                "message": "How many contacts have a score above 5?",
                "execute_query": True,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        # Query generated but not executed (no db_url)
        assert data["query"] is not None
        assert data["query_result"] is None
