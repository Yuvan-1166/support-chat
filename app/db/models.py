"""Database Models for Sessions and Chat Messages."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.db import Base


class SessionModel(Base):
    __tablename__ = "sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    last_accessed = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    query_type = Column(String(50), nullable=False)
    # Storing the JSON list of schema representation
    schema_context = Column(JSON, nullable=False)
    db_url = Column(String(2048), nullable=True)
    system_instructions = Column(Text, nullable=True)

    # 1:N relationship with chat messages
    messages = relationship(
        "ChatMessageModel",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessageModel.timestamp",
    )

    @property
    def has_db_connection(self) -> bool:
        return self.db_url is not None


class ChatMessageModel(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(36), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    
    role = Column(String(50), nullable=False)
    content = Column(Text, nullable=False)
    query = Column(Text, nullable=True)
    query_result = Column(JSON, nullable=True)
    insight = Column(Text, nullable=True)
    
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    session = relationship("SessionModel", back_populates="messages")
