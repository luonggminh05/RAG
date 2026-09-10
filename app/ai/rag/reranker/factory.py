from app.ai.rag.reranker.base import BaseReranker
from app.ai.rag.reranker.disabled import DisabledReranker
from app.core.config import settings

def get_reranker() -> BaseReranker:
    reranker_type = getattr(settings, "reranker_type", "disabled")
    if reranker_type == "flashrank":
        try:
            from app.ai.rag.reranker.flashrank_reranker import FlashRankReranker
            return FlashRankReranker()
        except Exception:
            return DisabledReranker()
    return DisabledReranker()
