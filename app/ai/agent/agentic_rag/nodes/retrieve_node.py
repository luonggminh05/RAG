"""
Retrieve Node cho RAG Fast Pipeline (app/ai/agent/agentic_rag/nodes/retrieve_node.py).
Truy xuất trực tiếp các chunks tài liệu thông qua Hybrid Search + Reranker,
loại bỏ hoàn toàn LLM Grader và Agent tool-call loop để đạt độ trễ tối ưu 2-3s.
"""

import logging
from typing import Any, Dict

from app.ai.agent.agentic_rag.state import AgenticRagState

logger = logging.getLogger(__name__)


def _get(state: Any, key: str, default: Any = None) -> Any:
    return state.get(key, default) if isinstance(state, dict) else getattr(state, key, default)


async def retrieve_rag_node(state: AgenticRagState) -> Dict[str, Any]:
    """
    Node 1 trong Fast Pipeline:
    Truy vấn Vector DB + Fulltext Search (RRF) kết hợp Reranker.
    """
    from app.routers.dependencies import get_vector_retriever

    user_query = _get(state, "user_query", "")
    user_roles = _get(state, "user_roles")
    user_department = _get(state, "user_department")
    messages = _get(state, "messages", [])
    top_k = _get(state, "top_k")

    if not user_query and messages:
        for m in reversed(messages):
            if hasattr(m, "content") and m.content and getattr(m, "type", "") in ("human", "user"):
                user_query = str(m.content)
                break

    logger.info("[RAG FAST-PIPELINE] Bắt đầu tra cứu tri thức cho câu hỏi: '%s'", str(user_query)[:80])

    try:
        retriever = get_vector_retriever()
        results = await retriever.retrieve_context(
            query=user_query,
            top_k=top_k,
            user_roles=user_roles,
            user_department=user_department,
        )

        raw_docs = results.get("documents") or []
        if raw_docs and isinstance(raw_docs[0], list):
            docs = raw_docs[0]
        elif isinstance(raw_docs, list):
            docs = raw_docs
        else:
            docs = []

        raw_cits = results.get("citations") or []
        if raw_cits and isinstance(raw_cits[0], list):
            citations = raw_cits[0]
        elif isinstance(raw_cits, list):
            citations = raw_cits
        else:
            citations = []

        logger.info(
            "[RAG FAST-PIPELINE] Tra cứu hoàn tất: %d chunks tài liệu trúng khớp sau Reranker.",
            len(docs),
        )

        return {
            "documents": docs,
            "citations": citations,
            "is_relevant": len(docs) > 0,
            "user_query": user_query,
        }

    except Exception as ex:
        logger.error("[RAG FAST-PIPELINE] Lỗi khi truy vấn retriever: %s", ex, exc_info=True)
        return {
            "documents": [],
            "citations": [],
            "is_relevant": False,
            "user_query": user_query,
        }
