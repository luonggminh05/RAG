import logging
from typing import Any, Dict, List, Optional
from app.ai.rag.embedding.service import TeiEmbeddingService
from app.ai.rag.reranker.base import BaseReranker
from app.ai.rag.reranker.disabled import DisabledReranker
from app.ai.rag.retrieval.query_analyzer import determine_dynamic_top_k
from app.ai.rag.text.normalizer import VietnameseNormalizer
from app.core.config import settings

logger = logging.getLogger(__name__)

class VectorRetriever:
    """Retriever truy vấn ngữ cảnh Hybrid Vector + FTS có phân quyền vai trò (User Roles RBAC) và Reranker."""

    def __init__(
        self,
        repository: Any,
        embedding_service: TeiEmbeddingService,
        reranker: Optional[BaseReranker] = None,
    ):
        self.repository = repository
        self.embedding_service = embedding_service
        self.reranker = reranker or DisabledReranker()

    async def retrieve_context(
        self,
        query: str,
        top_k: Optional[int] = None,
        content_kind: Optional[str] = None,
        user_roles: Optional[str] = None,
        user_department: Optional[str] = None,
    ) -> Dict[str, Any]:
        effective_top_k, analysis = determine_dynamic_top_k(query, requested_top_k=top_k)
        effective_query = VietnameseNormalizer.normalize(query, expand_acronyms=True) if query else ""

        logger.info(
            f"[RAG] Retrieving context for query='{query[:50]}' (normalized='{effective_query[:50]}'), "
            f"roles='{user_roles}', dept='{user_department}', dynamic_top_k={effective_top_k} (category={analysis.category.value})"
        )

        query_embedding, cache_hit = await self.embedding_service.embed_query_cached(effective_query)
        candidate_k = max(getattr(settings, "hybrid_top_k_candidates", 20), effective_top_k * 3)

        # Execute Search in DocumentRepository
        search_results = self.repository.search(
            query=effective_query,
            query_embedding=query_embedding,
            top_k=candidate_k,
            content_kind=content_kind,
            user_roles=user_roles,
            user_department=user_department,
        )

        raw_docs = (
            search_results.get("documents", [[]])[0]
            if search_results.get("documents")
            else []
        )

        # Rerank if results found
        if raw_docs:
            ranked_indices = self.reranker.rerank(effective_query, raw_docs, effective_top_k)
            results_filtered: Dict[str, List[List[Any]]] = {}
            for key in ["ids", "documents", "metadatas", "distances", "citations"]:
                raw_list = search_results.get(key, [[]])[0] if search_results.get(key) else []
                filtered_sub = [raw_list[i] for i in ranked_indices if i < len(raw_list)]
                results_filtered[key] = [filtered_sub]
            search_results = results_filtered

        documents = search_results.get("documents", [[]])[0] if search_results.get("documents") else []
        citations = search_results.get("citations", [[]])[0] if search_results.get("citations") else []
        sources = list(dict.fromkeys(c.get("source") for c in citations if isinstance(c, dict) and c.get("source")))

        logger.info(f"[OK] [RAG] Retrieved {len(documents)} chunks | Sources: {sources}")
        return search_results
