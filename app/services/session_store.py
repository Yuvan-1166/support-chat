"""In-memory session store with an abstract interface for future backends."""

from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any, Optional

from app.core.config import get_settings
from app.schemas.session import QueryType, SchemaTable

logger = logging.getLogger(__name__)


# ── Data container ───────────────────────────────────────────────────────


class Session:
    """Represents a single chat session."""

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
        self.created_at: datetime = datetime.utcnow()
        self.query_type = query_type
        self.schema_context = schema_context
        self.db_url = db_url
        self.system_instructions = system_instructions
        self.messages: list[dict[str, Any]] = []
        self.last_accessed: datetime = self.created_at

    @property
    def has_db_connection(self) -> bool:
        return self.db_url is not None

    def touch(self) -> None:
        """Update the last-accessed timestamp."""
        self.last_accessed = datetime.utcnow()

    def add_message(self, role: str, content: str, **extra: Any) -> dict[str, Any]:
        """Append a message to the conversation history and return it."""
        msg: dict[str, Any] = {
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat(),
            **extra,
        }
        self.messages.append(msg)
        self.touch()
        return msg

    def get_llm_history(self) -> list[dict[str, str]]:
        """Return conversation history formatted for the LLM (role + content only)."""
        return [{"role": m["role"], "content": m["content"]} for m in self.messages]


# ── Abstract base ────────────────────────────────────────────────────────


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


# ── In-memory implementation ─────────────────────────────────────────────


class InMemorySessionStore(SessionStoreBase):
    """Dictionary-backed session store with TTL eviction."""

    def __init__(self) -> None:
        self._store: dict[str, Session] = {}

    @property
    def _ttl(self) -> timedelta:
        return timedelta(seconds=get_settings().SESSION_TTL_SECONDS)

    # ── CRUD ─────────────────────────────────────────────────────────────

    def create(
        self,
        *,
        query_type: QueryType,
        schema_context: list[SchemaTable],
        db_url: Optional[str] = None,
        system_instructions: Optional[str] = None,
    ) -> Session:
        session = Session(
            query_type=query_type,
            schema_context=schema_context,
            db_url=db_url,
            system_instructions=system_instructions,
        )
        self._store[session.session_id] = session
        logger.info("Session created: %s (type=%s)", session.session_id, query_type.value)
        return session

    def get(self, session_id: str) -> Optional[Session]:
        session = self._store.get(session_id)
        if session is None:
            return None
        # Check TTL
        if datetime.utcnow() - session.last_accessed > self._ttl:
            logger.info("Session expired: %s", session_id)
            self._store.pop(session_id, None)
            return None
        session.touch()
        return session

    def delete(self, session_id: str) -> bool:
        removed = self._store.pop(session_id, None)
        if removed:
            logger.info("Session deleted: %s", session_id)
        return removed is not None

    def cleanup_expired(self) -> int:
        """Remove all sessions that have exceeded TTL. Returns count removed."""
        now = datetime.utcnow()
        expired = [
            sid
            for sid, s in self._store.items()
            if now - s.last_accessed > self._ttl
        ]
        for sid in expired:
            self._store.pop(sid, None)
        if expired:
            logger.info("Cleaned up %d expired sessions", len(expired))
        return len(expired)


# ── Singleton accessor ───────────────────────────────────────────────────

_session_store: Optional[InMemorySessionStore] = None


def get_session_store() -> InMemorySessionStore:
    """Return the global session store (lazily created)."""
    global _session_store
    if _session_store is None:
        _session_store = InMemorySessionStore()
    return _session_store
