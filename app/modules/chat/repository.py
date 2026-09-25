import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.modules.chat.model import Conversation, ChatMessage, MessageFeedback

logger = logging.getLogger(__name__)

class ChatRepository:
    def create_conversation(self, user_id: Optional[str] = None, title: str = "Cuộc hội thoại mới") -> int:
        db: Session = SessionLocal()
        try:
            conv = Conversation(user_id=user_id, title=title)
            db.add(conv)
            db.commit()
            db.refresh(conv)
            return int(conv.id)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _to_int_id(value: Any) -> Optional[int]:
        try:
            return int(value)
        except (ValueError, TypeError):
            return None

    def get_conversation(self, conversation_id: Any, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        int_id = self._to_int_id(conversation_id)
        if int_id is None:
            return None
        db: Session = SessionLocal()
        try:
            query = db.query(Conversation).filter(Conversation.id == int_id)
            if user_id:
                query = query.filter(Conversation.user_id == str(user_id))
            conv = query.first()
            if not conv:
                return None
            return {
                "id": conv.id,
                "user_id": conv.user_id,
                "title": conv.title,
                "is_pinned": bool(conv.is_pinned),
                "created_at": conv.created_at.isoformat() if conv.created_at else None,
                "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
            }
        finally:
            db.close()

    def list_conversations(
        self,
        user_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        pinned_only: bool = False,
    ) -> List[Dict[str, Any]]:
        db: Session = SessionLocal()
        try:
            query = db.query(Conversation)
            if user_id:
                query = query.filter(Conversation.user_id == str(user_id))
            if pinned_only:
                query = query.filter(Conversation.is_pinned == True)

            query = query.order_by(
                Conversation.is_pinned.desc(),
                Conversation.updated_at.desc(),
                Conversation.id.desc(),
            )
            convs = query.offset(offset).limit(limit).all()
            return [
                {
                    "id": c.id,
                    "user_id": c.user_id,
                    "title": c.title,
                    "is_pinned": bool(c.is_pinned),
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                    "updated_at": c.updated_at.isoformat() if c.updated_at else None,
                }
                for c in convs
            ]
        finally:
            db.close()

    def update_conversation_title(self, conversation_id: Any, title: str) -> None:
        int_id = self._to_int_id(conversation_id)
        if int_id is None:
            return
        db: Session = SessionLocal()
        try:
            conv = db.query(Conversation).filter(Conversation.id == int_id).first()
            if conv:
                conv.title = title
                conv.updated_at = datetime.now(timezone.utc)
                db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

    def touch_conversation(self, conversation_id: Any) -> None:
        int_id = self._to_int_id(conversation_id)
        if int_id is None:
            return
        db: Session = SessionLocal()
        try:
            conv = db.query(Conversation).filter(Conversation.id == int_id).first()
            if conv:
                conv.updated_at = datetime.now(timezone.utc)
                db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

    def delete_conversation(self, conversation_id: Any) -> bool:
        int_id = self._to_int_id(conversation_id)
        if int_id is None:
            return False
        db: Session = SessionLocal()
        try:
            conv = db.query(Conversation).filter(Conversation.id == int_id).first()
            if conv:
                db.delete(conv)
                db.commit()
                return True
            return False
        except Exception:
            db.rollback()
            return False
        finally:
            db.close()

    # ── Message Operations ──

    def add_message(
        self,
        conversation_id: Any,
        role: str,
        content: str,
        trace_id: Optional[str] = None,
    ) -> int:
        int_id = self._to_int_id(conversation_id)
        if int_id is None:
            raise ValueError(f"Invalid conversation_id: {conversation_id}")
        db: Session = SessionLocal()
        try:
            msg = ChatMessage(
                conversation_id=int_id,
                role=role,
                content=content,
                trace_id=trace_id,
            )
            db.add(msg)
            db.commit()
            db.refresh(msg)
            return int(msg.id)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def get_message(self, message_id: Any) -> Optional[Dict[str, Any]]:
        """Lấy chi tiết 1 tin nhắn theo message_id (gồm trace_id)."""
        msg_id = self._to_int_id(message_id)
        if msg_id is None:
            return None
        db: Session = SessionLocal()
        try:
            msg = db.query(ChatMessage).filter(ChatMessage.id == msg_id).first()
            if not msg:
                return None
            return {
                "id": msg.id,
                "conversation_id": msg.conversation_id,
                "role": msg.role,
                "content": msg.content,
                "trace_id": getattr(msg, "trace_id", None),
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
            }
        finally:
            db.close()

    def get_messages(
        self,
        conversation_id: Any,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        int_id = self._to_int_id(conversation_id)
        if int_id is None:
            return []
        db: Session = SessionLocal()
        try:
            msgs = (
                db.query(ChatMessage)
                .filter(ChatMessage.conversation_id == int_id)
                .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
                .offset(offset)
                .limit(limit)
                .all()
            )
            return [
                {
                    "id": m.id,
                    "conversation_id": m.conversation_id,
                    "role": m.role,
                    "content": m.content,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
                for m in msgs
            ]
        finally:
            db.close()

    def count_messages(self, conversation_id: Any) -> int:
        int_id = self._to_int_id(conversation_id)
        if int_id is None:
            return 0
        db: Session = SessionLocal()
        try:
            return db.query(ChatMessage).filter(ChatMessage.conversation_id == int_id).count()
        finally:
            db.close()

    def update_message_content(self, message_id: Any, content: str) -> bool:
        """Cập nhật nội dung của một tin nhắn cụ thể (Edit message)."""
        msg_id = self._to_int_id(message_id)
        if msg_id is None:
            return False
        db: Session = SessionLocal()
        try:
            msg = db.query(ChatMessage).filter(ChatMessage.id == msg_id).first()
            if msg:
                msg.content = content
                db.commit()
                return True
            return False
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def truncate_messages_after(self, conversation_id: Any, message_id: Any) -> None:
        """Xóa tất cả tin nhắn có id > message_id trong conversation để hỗ trợ Retry/Branching."""
        conv_id = self._to_int_id(conversation_id)
        msg_id = self._to_int_id(message_id)
        if conv_id is None or msg_id is None:
            return
        db: Session = SessionLocal()
        try:
            db.query(ChatMessage).filter(
                ChatMessage.conversation_id == conv_id,
                ChatMessage.id > msg_id,
            ).delete(synchronize_session=False)
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def truncate_messages_from(self, conversation_id: Any, message_id: Any) -> None:
        """Xóa tất cả tin nhắn có id >= message_id trong conversation (dùng khi retry một tin nhắn trợ lý)."""
        conv_id = self._to_int_id(conversation_id)
        msg_id = self._to_int_id(message_id)
        if conv_id is None or msg_id is None:
            return
        db: Session = SessionLocal()
        try:
            db.query(ChatMessage).filter(
                ChatMessage.conversation_id == conv_id,
                ChatMessage.id >= msg_id,
            ).delete(synchronize_session=False)
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def get_messages_up_to(
        self,
        conversation_id: Any,
        message_id: Any,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Lấy lịch sử hội thoại tính đến đúng mốc message_id."""
        conv_id = self._to_int_id(conversation_id)
        msg_id = self._to_int_id(message_id)
        if conv_id is None or msg_id is None:
            return []
        db: Session = SessionLocal()
        try:
            msgs = (
                db.query(ChatMessage)
                .filter(
                    ChatMessage.conversation_id == conv_id,
                    ChatMessage.id <= msg_id,
                )
                .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "id": m.id,
                    "conversation_id": m.conversation_id,
                    "role": m.role,
                    "content": m.content,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
                for m in msgs
            ]
        finally:
            db.close()

    # ── Feedback Operations ──

    def add_feedback(self, message_id: Any, rating: str, comment: Optional[str] = None) -> int:
        msg_id = self._to_int_id(message_id)
        if msg_id is None:
            raise ValueError(f"Invalid message_id: {message_id}")
        db: Session = SessionLocal()
        try:
            fb = MessageFeedback(
                message_id=msg_id,
                rating=rating,
                comment=comment,
            )
            db.add(fb)
            db.commit()
            db.refresh(fb)
            return int(fb.id)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def get_feedback_by_message(self, message_id: Any) -> Optional[Dict[str, Any]]:
        msg_id = self._to_int_id(message_id)
        if msg_id is None:
            return None
        db: Session = SessionLocal()
        try:
            fb = db.query(MessageFeedback).filter(MessageFeedback.message_id == msg_id).first()
            if not fb:
                return None
            return {
                "id": fb.id,
                "message_id": fb.message_id,
                "rating": fb.rating,
                "comment": fb.comment,
                "created_at": fb.created_at.isoformat() if fb.created_at else None,
            }
        finally:
            db.close()
