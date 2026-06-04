"""Test agent service basic functionality."""

import pytest
from unittest.mock import Mock, MagicMock, patch
from app.services.agent_service import AgentService, AgentState, AgentResponse
from app.services.agent_tools import AgentToolkit
from app.services.session_store import Session
from app.schemas.session import QueryType, SchemaField, SchemaTable
from app.services.translator import QueryTranslator


@pytest.fixture
def mock_session_store():
    """Mock session store."""
    return Mock()


@pytest.fixture
def mock_translator():
    """Mock translator."""
    return Mock(spec=QueryTranslator)


@pytest.fixture
def sample_session():
    """Create a sample session for testing."""
    return Session(
        query_type=QueryType.MYSQL,
        schema_context=[
            SchemaTable(
                name="contacts",
                description="Customer contacts",
                fields=[
                    SchemaField(name="id", type="INT", is_primary_key=True),
                    SchemaField(name="name", type="VARCHAR(255)"),
                    SchemaField(name="status", type="VARCHAR(50)"),
                ],
            )
        ],
    )


def test_agent_toolkit_instantiation(mock_session_store, mock_translator):
    """Test that AgentToolkit can be instantiated."""
    toolkit = AgentToolkit(mock_session_store, mock_translator)
    assert toolkit is not None
    assert len(toolkit.get_tools()) > 0
    print("✓ AgentToolkit instantiation works")


def test_toolkit_execute_query_no_question(mock_session_store, mock_translator):
    """Test execute_query tool with missing question parameter."""
    toolkit = AgentToolkit(mock_session_store, mock_translator)
    result = toolkit.call_tool(
        Mock(),
        "execute_query",
        {},  # Missing 'question'
    )
    assert not result.success
    assert "required" in result.error.lower()
    print("✓ Tool validation works")


def test_toolkit_search_schema(mock_session_store, mock_translator, sample_session):
    """Test search_schema tool."""
    toolkit = AgentToolkit(mock_session_store, mock_translator)
    result = toolkit.call_tool(
        sample_session,
        "search_schema",
        {"search_term": "contact"},
    )
    assert result.success
    assert result.data is not None
    print("✓ Search schema tool works")


def test_toolkit_create_task(mock_session_store, mock_translator):
    """Test create_task tool."""
    toolkit = AgentToolkit(mock_session_store, mock_translator)
    result = toolkit.call_tool(
        Mock(),
        "create_task",
        {
            "title": "Follow up with customer",
            "priority": "high",
        },
    )
    assert result.success
    assert "stub" in result.data.get("note", "").lower()
    print("✓ Create task tool works (stubbed)")


def test_agent_state_instantiation(sample_session):
    """Test that AgentState can be created."""
    state = AgentState(
        user_message="How many customers do we have?",
        session=sample_session,
    )
    assert state.user_message == "How many customers do we have?"
    assert state.session == sample_session
    print("✓ AgentState instantiation works")


def test_agent_response_model():
    """Test AgentResponse model."""
    response = AgentResponse(
        content="I found 42 customers.",
        agent_reasoning=[],
    )
    assert response.role == "assistant"
    assert response.content == "I found 42 customers."
    print("✓ AgentResponse model works")


if __name__ == "__main__":
    print("\nRunning Phase 1 Agent Tests...")
    import sys
    sys.path.insert(0, "/home/yuvan/Programs/Development/support-chat")
    
    # Create fixtures
    store = Mock()
    translator = Mock(spec=QueryTranslator)
    
    # Test toolkit
    toolkit_test = AgentToolkit(store, translator)
    assert toolkit_test is not None
    print("✓ AgentToolkit instantiation works")
    
    # Test tools
    result = toolkit_test.call_tool(Mock(), "execute_query", {})
    assert not result.success
    print("✓ Tool validation works")
    
    # Test session
    session = Session(
        query_type=QueryType.MYSQL,
        schema_context=[
            SchemaTable(
                name="contacts",
                description="Customer contacts",
                fields=[
                    SchemaField(name="id", type="INT", is_primary_key=True),
                    SchemaField(name="name", type="VARCHAR(255)"),
                ],
            )
        ],
    )
    
    result = toolkit_test.call_tool(session, "search_schema", {"search_term": "contact"})
    assert result.success
    print("✓ Search schema tool works")
    
    # Test response model
    response = AgentResponse(
        content="Test response",
        agent_reasoning=[],
    )
    assert response.role == "assistant"
    print("✓ AgentResponse model works")
    
    print("\n✅ All Phase 1 tests passed!")
