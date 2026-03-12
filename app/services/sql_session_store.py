"""Session store backed by a SQLAlchemy database."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session as DBSession

from app.core.config import get_settings
from app.db.models import ChatMessageModel, SessionModel
from app.schemas.session import QueryType, SchemaTable
from app.services.session_store import Session, SessionStoreBase

logger = logging.getLogger(__name__)


def _model_to_domain(model: SessionModel) -> Session:
    """Convert an ORM SessionModel to the domain Session object."""
    # Build the schema_context back from JSON
    schema_context = [SchemaTable(**table) for table in model.schema_context]
    
    session = Session(
        query_type=QueryType(model.query_type),
        schema_context=schema_context,
        db_url=model.db_url,
        system_instructions=model.system_instructions,
    )
    # Override generated init defaults with DB values
    session.session_id = model.id
    session.created_at = model.created_at
    session.last_accessed = model.last_accessed
    
    # Reload messages
    session.messages = [
        {
            "role": m.role,
            "content": m.content,
            "query": m.query,
            "query_result": m.query_result,
            "insight": m.insight,
            "timestamp": m.timestamp.isoformat(),
        }
        for m in model.messages
    ]
    return session


class SQLSessionStore(SessionStoreBase):
    """SQLAlchemy-backed session store."""

    def __init__(self, db: DBSession) -> None:
        self.db = db

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
        
        domain_session = Session(
            query_type=query_type,
            schema_context=schema_context,
            db_url=db_url,
            system_instructions=system_instructions,
        )
        
        model = SessionModel(
            id=domain_session.session_id,
            created_at=domain_session.created_at,
            last_accessed=domain_session.last_accessed,
            query_type=query_type.value,
            schema_context=[table.model_dump() for table in schema_context],
            db_url=db_url,
            system_instructions=system_instructions,
        )
        
        self.db.add(model)
        self.db.commit()
        
        logger.info("Session created in DB: %s (type=%s)", model.id, query_type.value)
        return domain_session

    def get(self, session_id: str) -> Optional[Session]:
        model = self.db.query(SessionModel).filter(SessionModel.id == session_id).first()
        if model is None:
            return None
            
        # Check TTL
        now = datetime.now(timezone.utc)
        last = model.last_accessed
        # Handle naive datetimes stored by older code: treat them as UTC.
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if now - last > self._ttl:
            logger.info("Session expired: %s", session_id)
            self.db.delete(model)
            self.db.commit()
            return None

        # Touch timestamp
        model.last_accessed = datetime.now(timezone.utc)
        self.db.commit()
        
        return _model_to_domain(model)

    def delete(self, session_id: str) -> bool:
        model = self.db.query(SessionModel).filter(SessionModel.id == session_id).first()
        if model:
            self.db.delete(model)
            self.db.commit()
            logger.info("Session deleted: %s", session_id)
            return True
        return False

    def cleanup_expired(self) -> int:
        """Remove all sessions that have exceeded TTL. Returns count removed."""
        now = datetime.now(timezone.utc)
        cutoff = now - self._ttl
        
        expired_sessions = self.db.query(SessionModel).filter(SessionModel.last_accessed < cutoff).all()
        count = len(expired_sessions)
        
        for model in expired_sessions:
            self.db.delete(model)
            
        if count > 0:
            self.db.commit()
            logger.info("Cleaned up %d expired sessions from DB", count)
            
        return count

    def add_message(self, session_id: str, role: str, content: str, **extra: Any) -> dict[str, Any]:
        """Append a message to the database for this session."""
        msg = ChatMessageModel(
            session_id=session_id,
            role=role,
            content=content,
            query=extra.get("query"),
            query_result=extra.get("query_result"),
            insight=extra.get("insight"),
            timestamp=datetime.now(timezone.utc),
        )
        self.db.add(msg)

        # Touch the session
        model = self.db.query(SessionModel).filter(SessionModel.id == session_id).first()
        if model:
            model.last_accessed = datetime.now(timezone.utc)
            
        self.db.commit()
        self.db.refresh(msg)
        
        return {
            "role": msg.role,
            "content": msg.content,
            "query": msg.query,
            "query_result": msg.query_result,
            "insight": msg.insight,
            "timestamp": msg.timestamp.isoformat(),
        }

def get_session_store(db: DBSession) -> SQLSessionStore:
    """Return a SQL session store configured for the current request's DB session."""
    return SQLSessionStore(db)
