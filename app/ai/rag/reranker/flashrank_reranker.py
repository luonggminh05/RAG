import logging
from typing import List
from app.ai.rag.reranker.base import BaseReranker

logger = logging.getLogger(__name__)

class FlashRankReranker(BaseReranker):
    def __init__(self, model_name: str = "ms-marco-MiniLM-L-6-v2"):
        try:
            from flashrank import Ranker
            self._ranker = Ranker(model_name=model_name)
            logger.info(f"[OK] FlashRankReranker initialized with model='{model_name}'")
        except ImportError:
            logger.warning("[WARN] Package 'flashrank' chưa cài đặt, fallback sang DisabledReranker behavior.")
            self._ranker = None

    def rerank(self, query: str, chunks: List[str], top_k: int) -> List[int]:
        if not chunks:
            return []
        if self._ranker is None:
            return list(range(min(top_k, len(chunks))))

        try:
            from flashrank import RerankRequest
            passages = [{"text": chunk} for chunk in chunks]
            req = RerankRequest(query=query, passages=passages)
            results = self._ranker.rerank(req)
            return [item["id"] if "id" in item else item.get("index", idx) for idx, item in enumerate(results[:top_k])]
        except Exception as ex:
            logger.error(f"[RERANK] FlashRank error, falling back to original order: {ex}")
            return list(range(min(top_k, len(chunks))))
