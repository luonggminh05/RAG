import asyncio
import logging
from typing import List, Tuple, Dict, Any, Optional
import httpx
from cachetools import TTLCache
from app.core.config import settings

logger = logging.getLogger(__name__)

class TeiEmbeddingService:
    def __init__(self):
        self.base_url = (getattr(settings, "tei_url", "http://localhost:8080") or "http://localhost:8080").rstrip("/") + "/"
        self.timeout = 300.0

        cache_size = getattr(settings, "search_query_embedding_cache_size", 1024)
        ttl = getattr(settings, "search_query_embedding_cache_ttl_seconds", 3600)
        self._cache = TTLCache(maxsize=max(cache_size, 100), ttl=max(ttl, 60))
        self._inflight_tasks: Dict[str, asyncio.Task] = {}

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []

        batch_size = getattr(settings, "ingestion_batch_size", 16)
        all_embeddings = []

        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                try:
                    response = await client.post("embed", json={
                        "inputs": batch,
                        "normalize": True,
                        "truncate": True
                    })
                    response.raise_for_status()
                    embeddings = response.json()

                    if not isinstance(embeddings, list) or len(embeddings) != len(batch):
                        raise ValueError("TEI returned an invalid embedding response format.")

                    all_embeddings.extend(embeddings)
                except Exception as ex:
                    logger.error(f"[EMBED] Error calling TEI embedding endpoint for batch starting at {i}: {ex}")
                    raise

        return all_embeddings

    async def embed_query_cached(self, query: str) -> Tuple[List[float], bool]:
        if not query or not query.strip():
            # Return dummy 0 vector with correct dimensions
            dims = getattr(settings, "embedding_dims", 1024)
            return [0.0] * dims, False

        cache_key = "query-embedding:" + self._normalize_cache_key(query)

        # 1. Cache hit
        if cache_key in self._cache:
            return self._cache[cache_key], True

        # 2. Inflight task joining
        if cache_key in self._inflight_tasks:
            logger.debug(f"[EMBED] Joining inflight request for: {query[:50]}")
            try:
                embeddings = await self._inflight_tasks[cache_key]
                return embeddings[0], True
            except Exception:
                pass

        # 3. Request embedding
        task = asyncio.create_task(self.embed_texts([query]))
        self._inflight_tasks[cache_key] = task
        try:
            embeddings = await task
            embedding = embeddings[0]
            self._cache[cache_key] = embedding
            return embedding, False
        except Exception as ex:
            logger.error(f"[EMBED] Error fetching query embedding from TEI: {ex}")
            raise
        finally:
            self._inflight_tasks.pop(cache_key, None)

    def _normalize_cache_key(self, text: str) -> str:
        return " ".join(text.strip().lower().split())
