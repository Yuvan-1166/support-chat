from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.db import get_db
from app.db.models import Base
from app.core.llm import LLMClient

# ── 1. Settings override ──────────────────────────────────────────────────

@pytest.fixture(scope="session")
def test_settings():
    """Provide test-friendly settings."""
    return Settings(
        GROQ_API_KEY="test-key-not-real",
        GROQ_MODEL="test-model",
        APP_ENV="development",
        LOG_LEVEL="DEBUG",
        SESSION_TTL_SECONDS=300,
        API_KEYS="",  # empty = dev mode, no auth required
        RATE_LIMIT="1000/minute",
        DATABASE_URL="sqlite:///:memory:"
    )

# ── 2. Test Database Setup ────────────────────────────────────────────────

@pytest.fixture(scope="function")
def test_db_session():
    """Create a fresh in-memory SQLite database for each test."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


# ── 3. Mock LLM Client ────────────────────────────────────────────────────

@pytest.fixture()
def mock_llm_client():
    client = MagicMock(spec=LLMClient)
    client.chat_completion.return_value = '{"query": "SELECT * FROM test", "explanation": "test explanation"}'
    client.chat_completion_json.return_value = {
        "query": "SELECT * FROM test",
        "explanation": "test explanation",
        "confidence": 0.95,
    }
    return client


# ── 4. Test Client with Overrides ─────────────────────────────────────────

@pytest.fixture()
def test_client(test_db_session, mock_llm_client, test_settings):
    from app.main import app
    from app.core.llm import get_llm_client
    from app.core.config import get_settings
    
    def override_get_db():
        try:
            yield test_db_session
        finally:
            pass

    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_llm_client] = lambda: mock_llm_client
    app.dependency_overrides[get_db] = override_get_db

    client = TestClient(app)
    yield client
    
    app.dependency_overrides.clear()
