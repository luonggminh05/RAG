import json
import logging
from contextvars import ContextVar
from typing import Optional, Any, List
from langchain_core.tools import tool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
_retriever = None

def _get_retriever():
    global _retriever
    if _retriever is None:
        from app.routers.dependencies import get_vector_retriever
        _retriever = get_vector_retriever()
    return _retriever


_user_roles_var: ContextVar[Optional[str]] = ContextVar("user_roles", default=None)
_user_department_var: ContextVar[Optional[str]] = ContextVar("user_department", default=None)
_chat_history_var: ContextVar[Optional[list]] = ContextVar("chat_history", default=None)

def set_rbac_context(
    user_roles: Optional[str] = None,
    user_department: Optional[str] = None,
    chat_history: Optional[list] = None,
) -> None:
    _user_roles_var.set(user_roles)
    _user_department_var.set(user_department)
    _chat_history_var.set(chat_history)

def get_rbac_context() -> dict:
    return {
        "user_roles": _user_roles_var.get(),
        "user_department": _user_department_var.get(),
        "chat_history": _chat_history_var.get(),
    }

class SearchPolicyDocsInput(BaseModel):
    query: str = Field(description="Câu hỏi hoặc từ khóa tra cứu quy chế, tài liệu, HDSD")
    top_k: int = Field(default=5, description="Số lượng đoạn văn bản trả về (1-10)")

@tool("search_policy_and_manual_docs", args_schema=SearchPolicyDocsInput)
async def search_policy_and_manual_docs(query: str, top_k: int = 5) -> str:
    """Tìm kiếm trong kho tài liệu quy chế, chính sách nội bộ, sổ tay HDSD."""
    try:
        retriever = _get_retriever()
        effective_query = query
        history = _chat_history_var.get()
        if history:
            try:
                from app.ai.rag.query.contextualizer import QueryContextualizer
                contextualizer = QueryContextualizer()
                effective_query = await contextualizer.rewrite(query, history=history)
            except Exception as ex:
                logger.debug(f"[TOOL] Query contextualization fallback: {ex}")
                effective_query = query

        result = await retriever.retrieve_context(
            query=effective_query,
            top_k=top_k,
            user_roles=_user_roles_var.get(),
            user_department=_user_department_var.get(),
        )
        documents = result.get("documents", [[]])[0] if result.get("documents") else []
        citations = result.get("citations", [[]])[0] if result.get("citations") else []
        return json.dumps({
            "documents": documents,
            "citations": citations,
            "query_used": effective_query,
        }, ensure_ascii=False)
    except Exception as e:
        logger.exception(f"[TOOL] search_policy_and_manual_docs error: {e}")
        return json.dumps({"documents": [], "citations": [], "error": str(e)})
