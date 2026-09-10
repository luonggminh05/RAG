import logging
from typing import Any, Dict, List, Optional
from app.core.config import settings

logger = logging.getLogger(__name__)

_langfuse_client = None

def setup_langfuse() -> None:
    """Khởi tạo Langfuse client toàn cục nếu enabled."""
    global _langfuse_client
    if not getattr(settings, "langfuse_enabled", False):
        logger.info("[LLMOPS] Langfuse tracing is disabled by config.")
        return

    try:
        from langfuse import Langfuse
        _langfuse_client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
        logger.info("[LLMOPS] Langfuse client successfully initialized.")
    except Exception as ex:
        logger.warning(f"[LLMOPS] Failed to initialize Langfuse client: {ex}")

def get_langfuse_client():
    """Lấy Langfuse client."""
    global _langfuse_client
    if _langfuse_client is None and getattr(settings, "langfuse_enabled", False):
        setup_langfuse()
    return _langfuse_client

def flush_langfuse() -> None:
    """Flush tất cả pending traces/spans trước khi ứng dụng shutdown."""
    global _langfuse_client
    if _langfuse_client:
        try:
            _langfuse_client.flush()
            logger.info("[LLMOPS] Langfuse flushed successfully on shutdown.")
        except Exception as ex:
            logger.warning(f"[LLMOPS] Error flushing Langfuse: {ex}")

def get_langfuse_callback_handler(
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    tags: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    trace_name: Optional[str] = None,
):
    """Tạo Langfuse CallbackHandler cho LangChain / LangGraph run."""
    if not getattr(settings, "langfuse_enabled", False):
        return None

    try:
        from langfuse.callback import CallbackHandler
        return CallbackHandler(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
            session_id=str(session_id) if session_id else None,
            user_id=str(user_id) if user_id else None,
            tags=tags or ["rag-service", "agentic-rag"],
            metadata=metadata or {},
            trace_name=trace_name or "AgenticRAG_ChatStream",
        )
    except Exception as ex:
        logger.warning(f"[LLMOPS] Could not load Langfuse CallbackHandler: {ex}")
        return None

def get_langfuse_langchain_config(
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    tags: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    trace_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Tạo RunnableConfig dictionary chứa callback cho LangGraph invocation."""
    handler = get_langfuse_callback_handler(
        session_id=session_id,
        user_id=user_id,
        tags=tags,
        metadata=metadata,
        trace_name=trace_name,
    )
    if handler:
        return {"callbacks": [handler]}
    return {}

def log_feedback_score(
    name: str = "user_feedback",
    value: float = 1.0,
    comment: Optional[str] = None,
    trace_id: Optional[str] = None,
    observation_id: Optional[str] = None,
) -> None:
    """Gửi feedback score (like/dislike) lên Langfuse dashboard."""
    client = get_langfuse_client()
    if not client:
        return
    try:
        client.score(
            name=name,
            value=value,
            comment=comment,
            trace_id=trace_id,
            observation_id=observation_id,
        )
        logger.debug(f"[LLMOPS] Logged Langfuse score '{name}'={value} (trace_id={trace_id})")
    except Exception as ex:
        logger.warning(f"[LLMOPS] Failed to send score to Langfuse: {ex}")
