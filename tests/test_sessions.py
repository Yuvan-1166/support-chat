"""Tests for session management endpoints."""

from __future__ import annotations

from unittest.mock import patch

from app.schemas.session import SchemaField, SchemaTable


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
                "description": "Main contacts table",
            }
        ],
    }
    payload.update(overrides)
    return test_client.post("/sessions", json=payload)


class TestCreateSession:
    def test_creates_session_successfully(self, test_client):
        resp = _create_session(test_client)
        assert resp.status_code == 201
        data = resp.json()
        assert "session_id" in data
        assert data["query_type"] == "mysql"
        assert data["has_db_connection"] is False

    def test_creates_session_with_db_url(self, test_client):
        resp = _create_session(test_client, db_url="mysql://localhost/test")
        assert resp.status_code == 201
        assert resp.json()["has_db_connection"] is True

    def test_allows_db_url_without_schema_context_via_auto_discovery(self, test_client):
        with patch("app.api.sessions.introspect_schema") as mock_introspect:
            mock_introspect.return_value = [
                SchemaTable(
                    name="users",
                    description="Auto-discovered from database metadata",
                    fields=[SchemaField(name="id", type="INT", is_primary_key=True)],
                )
            ]

            resp = test_client.post(
                "/sessions",
                json={
                    "query_type": "mysql",
                    "db_url": "mysql://localhost/test",
                    "schema_context": [],
                },
            )

        assert resp.status_code == 201
        assert resp.json()["has_db_connection"] is True

    def test_rejects_when_no_schema_context_and_no_db_url(self, test_client):
        resp = test_client.post(
            "/sessions",
            json={
                "query_type": "mysql",
                "schema_context": [],
            },
        )
        assert resp.status_code == 422

    def test_rejects_invalid_query_type(self, test_client):
        resp = _create_session(test_client, query_type="invalid")
        assert resp.status_code == 422


class TestGetSession:
    def test_returns_session_info(self, test_client):
        create_resp = _create_session(test_client)
        session_id = create_resp.json()["session_id"]

        resp = test_client.get(f"/sessions/{session_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == session_id
        assert data["message_count"] == 0

    def test_returns_404_for_unknown_session(self, test_client):
        resp = test_client.get("/sessions/nonexistent")
        if resp.status_code != 404:
            print("ERROR BODY:", resp.text)
        assert resp.status_code == 404


class TestGetHistory:
    def test_returns_empty_history(self, test_client):
        create_resp = _create_session(test_client)
        session_id = create_resp.json()["session_id"]

        resp = test_client.get(f"/sessions/{session_id}/history")
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == session_id
        assert data["messages"] == []

    def test_returns_404_for_unknown_session(self, test_client):
        resp = test_client.get("/sessions/nonexistent/history")
        assert resp.status_code == 404


class TestDeleteSession:
    def test_deletes_session(self, test_client):
        create_resp = _create_session(test_client)
        session_id = create_resp.json()["session_id"]

        resp = test_client.delete(f"/sessions/{session_id}")
        assert resp.status_code == 204

        # Verify it's gone
        resp = test_client.get(f"/sessions/{session_id}")
        assert resp.status_code == 404

    def test_returns_404_for_unknown_session(self, test_client):
        resp = test_client.delete("/sessions/nonexistent")
        assert resp.status_code == 404
