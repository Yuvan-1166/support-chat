"""Tests for session management endpoints."""

from __future__ import annotations


def _create_session(client, **overrides):
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
                "description": "Main contacts table",
            }
        ],
    }
    payload.update(overrides)
    return client.post("/sessions", json=payload)


class TestCreateSession:
    def test_creates_session_successfully(self, client):
        resp = _create_session(client)
        assert resp.status_code == 201
        data = resp.json()
        assert "session_id" in data
        assert data["query_type"] == "mysql"
        assert data["has_db_connection"] is False

    def test_creates_session_with_db_url(self, client):
        resp = _create_session(client, db_url="mysql://localhost/test")
        assert resp.status_code == 201
        assert resp.json()["has_db_connection"] is True

    def test_rejects_invalid_query_type(self, client):
        resp = _create_session(client, query_type="invalid")
        assert resp.status_code == 422


class TestGetSession:
    def test_returns_session_info(self, client):
        create_resp = _create_session(client)
        session_id = create_resp.json()["session_id"]

        resp = client.get(f"/sessions/{session_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == session_id
        assert data["message_count"] == 0

    def test_returns_404_for_unknown_session(self, client):
        resp = client.get("/sessions/nonexistent")
        assert resp.status_code == 404


class TestGetHistory:
    def test_returns_empty_history(self, client):
        create_resp = _create_session(client)
        session_id = create_resp.json()["session_id"]

        resp = client.get(f"/sessions/{session_id}/history")
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == session_id
        assert data["messages"] == []

    def test_returns_404_for_unknown_session(self, client):
        resp = client.get("/sessions/nonexistent/history")
        assert resp.status_code == 404


class TestDeleteSession:
    def test_deletes_session(self, client):
        create_resp = _create_session(client)
        session_id = create_resp.json()["session_id"]

        resp = client.delete(f"/sessions/{session_id}")
        assert resp.status_code == 204

        # Verify it's gone
        resp = client.get(f"/sessions/{session_id}")
        assert resp.status_code == 404

    def test_returns_404_for_unknown_session(self, client):
        resp = client.delete("/sessions/nonexistent")
        assert resp.status_code == 404
