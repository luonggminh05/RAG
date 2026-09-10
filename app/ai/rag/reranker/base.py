from abc import ABC, abstractmethod
from typing import List

class BaseReranker(ABC):
    @abstractmethod
    def rerank(self, query: str, chunks: List[str], top_k: int) -> List[int]:
        """Trả về danh sách indices sắp xếp giảm dần theo relevance score."""
        pass
