"""Shared pytest fixtures."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings


@pytest.fixture(autouse=True)
def _override_settings():
    """Provide test-friendly settings for every test."""
    test_settings = Settings(
        GROQ_API_KEY="test-key-not-real",
        GROQ_MODEL="test-model",
        APP_ENV="development",
        LOG_LEVEL="DEBUG",
        SESSION_TTL_SECONDS=300,
        API_KEYS="",  # empty = dev mode, no auth required
        RATE_LIMIT="1000/minute",
    )
    with patch("app.core.config.get_settings", return_value=test_settings):
        yield test_settings


@pytest.fixture()
def mock_llm_client():
    """Return a mocked LLM client that returns predictable JSON."""
    client = MagicMock()
    client.chat_completion_json.return_value = {
        "query": "SELECT COUNT(*) FROM contacts WHERE score > 5",
        "explanation": "Counts contacts with score above 5",
        "confidence": 0.95,
    }
    client.chat_completion.return_value = (
        "There are 42 contacts with a score above 5."
    )
    return client


@pytest.fixture()
def _patch_llm(mock_llm_client):
    """Patch the global LLM client singleton."""
    with patch("app.core.llm.get_llm_client", return_value=mock_llm_client):
        # Also reset the chat service singleton so it picks up the mock
        with patch("app.services.chat_service._chat_service", None):
            yield mock_llm_client


@pytest.fixture()
def fresh_session_store():
    """Provide a fresh in-memory session store and patch the singleton."""
    from app.services.session_store import InMemorySessionStore

    store = InMemorySessionStore()
    with patch("app.services.session_store.get_session_store", return_value=store):
        yield store


@pytest.fixture()
def client(fresh_session_store, _patch_llm):
    """FastAPI TestClient with mocked dependencies."""
    from app.main import app

    with TestClient(app) as c:
        yield c
