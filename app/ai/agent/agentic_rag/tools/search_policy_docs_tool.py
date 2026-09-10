import json
import logging
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

_rbac_context: dict[str, Any] = {"user_roles": None, "user_department": None, "chat_history": None}

def set_rbac_context(
    user_roles: Optional[str] = None,
    user_department: Optional[str] = None,
    chat_history: Optional[list] = None,
) -> None:
    _rbac_context["user_roles"] = user_roles
    _rbac_context["user_department"] = user_department
    _rbac_context["chat_history"] = chat_history

class SearchPolicyDocsInput(BaseModel):
    query: str = Field(description="Câu hỏi hoặc từ khóa tra cứu quy chế, tài liệu, HDSD")
    top_k: int = Field(default=5, description="Số lượng đoạn văn bản trả về (1-10)")

@tool("search_policy_and_manual_docs", args_schema=SearchPolicyDocsInput)
async def search_policy_and_manual_docs(query: str, top_k: int = 5) -> str:
    """Tìm kiếm trong kho tài liệu quy chế, chính sách nội bộ, sổ tay HDSD."""
    try:
        retriever = _get_retriever()
        effective_query = query
        history = _rbac_context.get("chat_history")
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
            user_roles=_rbac_context.get("user_roles"),
            user_department=_rbac_context.get("user_department"),
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
