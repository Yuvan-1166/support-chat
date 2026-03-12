"""Abstract base class for session stores."""

from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Optional

from app.schemas.session import QueryType, SchemaTable

logger = logging.getLogger(__name__)

class Session:
    """Represents a single chat session domain model."""

    __slots__ = (
        "session_id",
        "created_at",
        "query_type",
        "schema_context",
        "db_url",
        "system_instructions",
        "messages",
        "last_accessed",
    )

    def __init__(
        self,
        *,
        query_type: QueryType,
        schema_context: list[SchemaTable],
        db_url: Optional[str] = None,
        system_instructions: Optional[str] = None,
    ) -> None:
        self.session_id: str = uuid.uuid4().hex
        self.created_at: datetime = datetime.now(timezone.utc)
        self.query_type = query_type
        self.schema_context = schema_context
        self.db_url = db_url
        self.system_instructions = system_instructions
        self.messages: list[dict[str, Any]] = []
        self.last_accessed: datetime = self.created_at

    @property
    def has_db_connection(self) -> bool:
        return self.db_url is not None

    def get_llm_history(self) -> list[dict[str, str]]:
        """Return conversation history formatted for the LLM (role + content only)."""
        return [{"role": m["role"], "content": m["content"]} for m in self.messages]


class SessionStoreBase(ABC):
    """Interface for session persistence backends."""

    @abstractmethod
    def create(
        self,
        *,
        query_type: QueryType,
        schema_context: list[SchemaTable],
        db_url: Optional[str] = None,
        system_instructions: Optional[str] = None,
    ) -> Session: ...

    @abstractmethod
    def get(self, session_id: str) -> Optional[Session]: ...

    @abstractmethod
    def delete(self, session_id: str) -> bool: ...

    @abstractmethod
    def cleanup_expired(self) -> int: ...

    @abstractmethod
    def add_message(self, session_id: str, role: str, content: str, **extra: Any) -> dict[str, Any]: ...

