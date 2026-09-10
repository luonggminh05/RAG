from datetime import datetime, timezone
from sqlalchemy import (
    Boolean, Column, Integer, String, Text, DateTime, ForeignKey, Index, Unicode, UnicodeText
)
from sqlalchemy.orm import relationship

from app.core.database import Base

class Conversation(Base):
    __tablename__ = "Conversations"

    id = Column("Id", Integer, primary_key=True, autoincrement=True)
    user_id = Column("UserId", Unicode(200), nullable=True, index=True)
    user_roles = Column("UserRoles", Unicode(500), nullable=True)
    user_department = Column("UserDepartment", Unicode(100), nullable=True)
    is_pinned = Column("IsPinned", Boolean, nullable=False, default=False, server_default="0")
    pinned_at = Column("PinnedAt", DateTime, nullable=True)
    title_source = Column("TitleSource", String(20), nullable=False, default="default", server_default="default")
    title = Column("Title", Unicode(255), nullable=True, default="Cuộc hội thoại mới")
    created_at = Column("CreatedAt", DateTime, nullable=True, default=datetime.utcnow)
    updated_at = Column("UpdatedAt", DateTime, nullable=True, default=datetime.utcnow, onupdate=datetime.utcnow)

    messages = relationship("ChatMessage", back_populates="conversation", cascade="all, delete-orphan")


class ChatMessage(Base):
    __tablename__ = "ChatMessages"

    id = Column("Id", Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(
        "ConversationId", Integer,
        ForeignKey("Conversations.Id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    role = Column("Role", String(20), nullable=True)   # 'user' | 'assistant' | 'system'
    content = Column("Content", UnicodeText, nullable=True)
    trace_id = Column("TraceId", String(100), nullable=True)
    created_at = Column("CreatedAt", DateTime, nullable=True, default=datetime.utcnow)

    conversation = relationship("Conversation", back_populates="messages")


class MessageFeedback(Base):
    __tablename__ = "MessageFeedback"

    id = Column("Id", Integer, primary_key=True, autoincrement=True)
    message_id = Column(
        "MessageId", Integer,
        ForeignKey("ChatMessages.Id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rating = Column("Rating", String(20), nullable=False)  # 'positive' | 'negative'
    comment = Column("Comment", UnicodeText, nullable=True)
    created_at = Column("CreatedAt", DateTime, nullable=False, default=datetime.utcnow)

    message = relationship("ChatMessage", backref="feedbacks")


Index("IX_Conversations_User_Pinned_Updated", Conversation.user_id, Conversation.is_pinned, Conversation.updated_at)
