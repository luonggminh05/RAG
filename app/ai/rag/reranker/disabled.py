from typing import List
from app.ai.rag.reranker.base import BaseReranker

class DisabledReranker(BaseReranker):
    def rerank(self, query: str, chunks: List[str], top_k: int) -> List[int]:
        return list(range(min(top_k, len(chunks))))
