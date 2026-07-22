import asyncio
import logging
import httpx
from typing import List, Tuple
from cachetools import TTLCache
from app.config import settings

logger = logging.getLogger(__name__)

class TeiEmbeddingService:
    def __init__(self):
        self.base_url = settings.tei_url.rstrip("/") + "/"
        self.timeout = 120.0
        
        # In-memory cache for query embeddings
        # limit by settings or default
        cache_size = settings.search_query_embedding_cache_size if settings.search_query_embedding_cache_size > 0 else 1024
        ttl = settings.search_query_embedding_cache_ttl_seconds if settings.search_query_embedding_cache_ttl_seconds > 0 else 3600
        self._cache = TTLCache(maxsize=cache_size, ttl=ttl)
        
        # Dictionary to track concurrent inflight tasks for the same query to prevent redundant API calls
        self._inflight_tasks = {}

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []

        batch_size = settings.ingestion_batch_size if settings.ingestion_batch_size > 0 else 32
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
                    logger.error(f"Error calling TEI embedding endpoint for batch starting at {i}: {ex}")
                    raise

        return all_embeddings

    async def embed_query_cached(self, query: str) -> Tuple[List[float], bool]:
        if settings.search_query_embedding_cache_size <= 0:
            embeddings = await self.embed_texts([query])
            return embeddings[0], False

        cache_key = "query-embedding:" + self._normalize_cache_key(query)
        
        # 1. Check cache hit
        if cache_key in self._cache:
            return self._cache[cache_key], True

        # 2. Check duplicate concurrent request
        if cache_key in self._inflight_tasks:
            logger.info(f"Joining duplicate inflight embedding request for: {query}")
            try:
                embeddings = await self._inflight_tasks[cache_key]
                return embeddings[0], True
            except Exception:
                # If the joined task failed, retry embedding in this execution path
                pass

        # 3. Create new task
        task = asyncio.create_task(self.embed_texts([query]))
        self._inflight_tasks[cache_key] = task
        try:
            embeddings = await task
            embedding = embeddings[0]
            self._cache[cache_key] = embedding
            return embedding, False
        except Exception as ex:
            logger.error(f"Error fetching query embedding from TEI: {ex}")
            raise
        finally:
            self._inflight_tasks.pop(cache_key, None)

    def _normalize_cache_key(self, text: str) -> str:
        return " ".join(text.strip().lower().split())
