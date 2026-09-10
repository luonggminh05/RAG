import asyncio
import hashlib
import logging
import os
import io
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.ai.rag.chunking.splitter import TextChunker, ChunkResult
from app.ai.rag.embedding.service import TeiEmbeddingService
from app.ai.rag.ingestion.extractor import FileTextExtractor, IngestedDocument
from app.ai.rag.text.normalizer import VietnameseNormalizer
from app.core.config import settings
from app.llmops.langfuse import get_langfuse_client, flush_langfuse

logger = logging.getLogger(__name__)


class IngestionPipeline:
    """Pipeline xử lý ngầm Ingestion hoàn chỉnh (Background Task)."""

    def __init__(self, repository: Any, embedding_service: TeiEmbeddingService):
        self.repository = repository
        self.embedding_service = embedding_service
        self.extractor = FileTextExtractor()
        self.chunker = TextChunker()

    def run_sync(
        self,
        task_id: str,
        temp_path: str,
        file_name: str,
        file_size: int,
        metadata: Dict[str, Any],
    ) -> None:
        """Entrypoint đồng bộ cho BackgroundTasks."""
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(
                self._run_async(task_id, temp_path, file_name, file_size, metadata)
            )
        finally:
            loop.close()

    async def _run_async(
        self,
        task_id: str,
        temp_path: str,
        file_name: str,
        file_size: int,
        metadata: Dict[str, Any],
    ) -> Tuple[bool, int]:
        backend_id_raw = (
            metadata.get("backend_document_id")
            or metadata.get("backendId")
            or metadata.get("backend_id")
            or metadata.get("id")
            or "0"
        )
        backend_id = int(backend_id_raw) if str(backend_id_raw).isdigit() else 0

        client = get_langfuse_client()
        trace = None
        if client:
            try:
                trace = client.trace(
                    name="DocumentIngestion",
                    id=task_id,
                    metadata={"file_name": file_name, "file_size": file_size, "backend_id": backend_id},
                )
            except Exception:
                trace = None

        try:
            logger.info(
                f"[PIPELINE] Starting ingestion task={task_id} for '{file_name}' (backend_id={backend_id})..."
            )

            # 1. Update status = PROCESSING, progress = 10%
            self.repository.update_ingestion_task(
                task_id=task_id, status="PROCESSING", progress_percent=10
            )
            if backend_id > 0:
                try:
                    self.repository.update_rag_document_status(
                        backend_id, "Processing", 0
                    )
                except Exception as ex:
                    logger.warning(f"[WARN] Could not update RagDocument status: {ex}")

            # 2. Extract Document Pages / Blocks
            extract_span = None
            if trace:
                try:
                    extract_span = trace.span(
                        name="extract",
                        input={"file_name": file_name, "file_path": temp_path, "file_size": file_size},
                    )
                except Exception:
                    extract_span = None

            extracted_docs: List[IngestedDocument] = await self.extractor.extract(
                temp_path, file_name
            )

            if extract_span:
                try:
                    extract_span.end(
                        output={"file_name": file_name, "page_count": len(extracted_docs)}
                    )
                except Exception:
                    pass

            self.repository.update_ingestion_task(
                task_id=task_id, status="PROCESSING", progress_percent=30
            )

            if not extracted_docs:
                logger.warning(f"[PIPELINE] No content extracted from '{file_name}'")
                self.repository.update_ingestion_task(
                    task_id=task_id,
                    status="COMPLETED",
                    progress_percent=100,
                    chunk_count=0,
                )
                if backend_id > 0:
                    self.repository.update_rag_document_status(
                        backend_id, "Completed", 0
                    )
                if trace:
                    try:
                        trace.update(output={"status": "COMPLETED", "chunk_count": 0})
                    except Exception:
                        pass
                flush_langfuse()
                return True, 0

            # 3. Chunking & Enrichment
            chunk_span = None
            if trace:
                try:
                    chunk_span = trace.span(
                        name="chunk",
                        input={"file_name": file_name, "doc_count": len(extracted_docs)},
                    )
                except Exception:
                    chunk_span = None

            final_chunks: List[Tuple[str, Dict[str, Any]]] = []
            allowed_roles = metadata.get("allowed_roles") or metadata.get("allowedRoles") or []
            if isinstance(allowed_roles, str):
                allowed_roles = [r.strip() for r in allowed_roles.split(",") if r.strip()]

            access_scope = metadata.get("access_scope") or metadata.get("accessScope") or "Public"
            owner_dept = metadata.get("owner_department") or metadata.get("ownerDepartment") or ""

            use_hierarchical = bool(
                metadata.get("hierarchical")
                or metadata.get("hierarchical_chunking")
                or getattr(settings, "ingestion_hierarchical_chunking", False)
            )

            ext = os.path.splitext(file_name)[1].lower()
            is_tabular = ext in [".xlsx", ".csv"]

            for doc_item in extracted_docs:
                raw_text = doc_item.page_content
                doc_meta = dict(doc_item.metadata)

                # Merge global RBAC metadata
                doc_meta["source"] = file_name
                doc_meta["backend_document_id"] = backend_id
                doc_meta["backendId"] = str(backend_id)
                doc_meta["accessScope"] = access_scope
                doc_meta["allowedRoles"] = allowed_roles
                if owner_dept:
                    doc_meta["owner_department"] = owner_dept

                # Determine if we should bypass text splitter (e.g. tabular row or vision image)
                content_kind = str(doc_meta.get("content_kind", ""))
                instruction_role = str(doc_meta.get("instruction_role", ""))
                doc_type = str(doc_meta.get("type", ""))

                bypass = is_tabular or content_kind == "image_ui_description" or instruction_role == "procedure_steps"

                if bypass:
                    norm_text = VietnameseNormalizer.normalize(raw_text, expand_acronyms=True)
                    if norm_text:
                        final_chunks.append((norm_text, doc_meta))
                elif use_hierarchical:
                    hierarchical_pairs = self.chunker.split_hierarchical(raw_text)
                    for child_chunk, parent_chunk in hierarchical_pairs:
                        chunk_meta = dict(doc_meta)
                        chunk_meta.update(child_chunk.metadata)
                        c_norm = VietnameseNormalizer.normalize(child_chunk.text, expand_acronyms=True)
                        if c_norm:
                            final_chunks.append((c_norm, chunk_meta))
                else:
                    # Markdown Breadcrumbs chunking
                    sub_chunks = self.chunker.split_markdown_with_context(raw_text)
                    if not sub_chunks:
                        raw_splits = self.chunker.split_text(raw_text)
                        for s in raw_splits:
                            s_norm = VietnameseNormalizer.normalize(s, expand_acronyms=True)
                            if s_norm:
                                final_chunks.append((s_norm, dict(doc_meta)))
                    else:
                        for chunk_res in sub_chunks:
                            chunk_meta = dict(doc_meta)
                            chunk_meta.update(chunk_res.metadata)
                            c_norm = VietnameseNormalizer.normalize(chunk_res.text, expand_acronyms=True)
                            if c_norm:
                                final_chunks.append((c_norm, chunk_meta))

            if chunk_span:
                try:
                    chunk_span.end(output={"chunk_count": len(final_chunks)})
                except Exception:
                    pass

            self.repository.update_ingestion_task(
                task_id=task_id, status="PROCESSING", progress_percent=60
            )

            if not final_chunks:
                logger.warning(f"[PIPELINE] 0 chunks produced for '{file_name}'")
                self.repository.update_ingestion_task(
                    task_id=task_id,
                    status="COMPLETED",
                    progress_percent=100,
                    chunk_count=0,
                )
                if backend_id > 0:
                    self.repository.update_rag_document_status(
                        backend_id, "Completed", 0
                    )
                if trace:
                    try:
                        trace.update(output={"status": "COMPLETED", "chunk_count": 0})
                    except Exception:
                        pass
                flush_langfuse()
                return True, 0

            # 4. Generate Embeddings & IDs
            chunk_texts = [c[0] for c in final_chunks]
            chunk_metas = [c[1] for c in final_chunks]

            embed_span = None
            if trace:
                try:
                    embed_span = trace.span(
                        name="embed",
                        input={"batch_count": len(chunk_texts), "model": getattr(settings, "embedding_model", "BAAI/bge-m3")},
                    )
                except Exception:
                    embed_span = None

            t_embed_start = asyncio.get_event_loop().time()
            embeddings = await self.embedding_service.embed_texts(chunk_texts)
            embed_duration_ms = (asyncio.get_event_loop().time() - t_embed_start) * 1000

            if embed_span:
                try:
                    embed_span.end(
                        output={"batch_count": len(chunk_texts), "embed_latency_ms": round(embed_duration_ms, 1)}
                    )
                except Exception:
                    pass

            self.repository.update_ingestion_task(
                task_id=task_id, status="PROCESSING", progress_percent=85
            )

            chunk_ids = []
            parent_ids = []
            for idx in range(len(chunk_texts)):
                c_id = f"{task_id}_chunk_{idx}"
                chunk_ids.append(c_id)
                chunk_metas[idx]["chunk_id"] = c_id
                
                p_id = chunk_metas[idx].get("parent_chunk_id") or chunk_metas[idx].get("ParentChunkId")
                if not p_id and "parent_idx" in chunk_metas[idx]:
                    p_id = f"{task_id}_parent_{chunk_metas[idx]['parent_idx']}"
                    chunk_metas[idx]["parent_chunk_id"] = p_id
                parent_ids.append(p_id)

            # 5. Delete old chunks & Upsert new chunks
            upsert_span = None
            if trace:
                try:
                    upsert_span = trace.span(
                        name="upsert",
                        input={"chunk_count": len(chunk_ids), "backend_id": backend_id},
                    )
                except Exception:
                    upsert_span = None

            if backend_id > 0:
                self.repository.delete_documents_by_backend_id(backend_id, file_name=file_name)
            else:
                self.repository.delete_documents_for_file(file_name)

            self.repository.upsert_documents(
                ids=chunk_ids,
                documents=chunk_texts,
                metadatas=chunk_metas,
                embeddings=embeddings,
                parent_chunk_ids=parent_ids,
            )

            if upsert_span:
                try:
                    upsert_span.end(output={"chunk_count": len(chunk_ids)})
                except Exception:
                    pass

            # 6. Update Task & Document Status = Completed, 100%
            chunk_count = len(chunk_ids)
            self.repository.update_ingestion_task(
                task_id=task_id,
                status="COMPLETED",
                progress_percent=100,
                chunk_count=chunk_count,
            )
            if backend_id > 0:
                self.repository.update_rag_document_status(
                    backend_id, "Completed", chunk_count
                )

            if trace:
                try:
                    trace.update(output={"status": "COMPLETED", "chunk_count": chunk_count})
                except Exception:
                    pass
            flush_langfuse()

            logger.info(
                f"[OK] [PIPELINE] Ingestion task={task_id} completed successfully with {chunk_count} chunks!"
            )
            return True, chunk_count

        except Exception as ex:
            err_msg = str(ex)
            logger.exception(f"[FAIL] [PIPELINE] Ingestion task={task_id} error: {err_msg}")
            if trace:
                try:
                    trace.update(output={"status": "FAILED", "error": err_msg})
                except Exception:
                    pass
            flush_langfuse()
            self.repository.update_ingestion_task(
                task_id=task_id,
                status="FAILED",
                progress_percent=0,
                error_message=err_msg,
            )
            if backend_id > 0:
                try:
                    self.repository.update_rag_document_status(
                        backend_id, "Failed", 0, error=err_msg
                    )
                except Exception:
                    pass
            return False, 0

        finally:
            # Clean up temp file
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception:
                pass
