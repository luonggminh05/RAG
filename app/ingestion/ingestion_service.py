import datetime
import hashlib
import io
import logging
import os
from typing import List, Dict, Any, Optional, Tuple
from app.config import settings
from app.ingestion.normalizer import VietnameseNormalizer
from app.ingestion.text_splitter import TextSplitter, SemanticChunker, IngestedDocument
from app.ingestion.parsers.base import DocumentParser
from app.services.tei_embedding import TeiEmbeddingService
from app.data.sql_repository import SqlDocumentRepository

logger = logging.getLogger(__name__)

class IngestionService:
    def __init__(self, parser_registry: DocumentParser, embedding_service: TeiEmbeddingService, repository: SqlDocumentRepository):
        self.parser_registry = parser_registry
        self.embedding_service = embedding_service
        self.repository = repository

    def _should_bypass_splitter(self, metadata: Dict[str, Any], is_tabular: bool) -> bool:
        doc_type = str(metadata.get("type", ""))
        instruction_role = str(metadata.get("instruction_role", ""))
        content_kind = str(metadata.get("content_kind", ""))

        is_slide = doc_type.startswith("pptx_slide")
        is_procedure = instruction_role == "procedure_steps"
        is_vision = content_kind == "image_ui_description"

        return is_tabular or is_slide or is_procedure or is_vision

    def _convert_to_markdown(self, text: str) -> str:
        """
        Chuyển đổi nội dung văn bản thuần túy (đã qua OCR/parse) sang định dạng Markdown
        bằng thư viện markitdown. Toàn bộ quá trình thực hiện trong bộ nhớ (in-memory),
        không ghi file xuống đĩa.

        Trả về Markdown string nếu thành công, hoặc text gốc nếu có lỗi.
        """
        if not text or not text.strip():
            return text
        try:
            from markitdown import MarkItDown
            md_converter = MarkItDown()
            # Đưa text vào BytesIO stream, dùng extension .txt để markitdown nhận diện plain-text
            stream = io.BytesIO(text.encode("utf-8"))
            result = md_converter.convert_stream(stream, file_extension=".txt")
            converted = result.text_content
            return converted if converted and converted.strip() else text
        except Exception as ex:
            logger.warning(f"MarkItDown conversion failed, falling back to original text: {ex}")
            return text

    async def ingest_file(
        self,
        file_path: str,
        file_name: str,
        custom_metadata: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, int]:
        # Check file details
        if not os.path.exists(file_path):
            logger.error(f"Ingest failed: file path does not exist '{file_path}'")
            return False, 0

        # Build file properties
        file_length = os.path.getsize(file_path)
        mtime = os.path.getmtime(file_path)
        last_write_time_utc = datetime.datetime.fromtimestamp(mtime, tz=datetime.timezone.utc)
        
        # Calculate file MD5 fingerprint
        hasher = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)
        fingerprint = hasher.hexdigest()

        # relative_path is used as stable identifier in IngestionFiles
        backend_document_id = custom_metadata.get("backend_document_id") if custom_metadata else None
        storage_key = custom_metadata.get("storage_key") if custom_metadata else None
        if backend_document_id and storage_key:
            relative_path = f"uploads/{backend_document_id}/{storage_key}"
        else:
            relative_path = f"uploads/{file_name}"
        logger.info(f"Ingesting file: {file_name} (path: {relative_path})")

        # Select parser
        ext = os.path.splitext(file_name)[1].lower()
        try:
            parser = self.parser_registry.get_parser(ext)
        except ValueError as ex:
            logger.error(f"Ingest failed: {ex}")
            return False, 0

        is_tabular = ext in [".xlsx", ".csv"]

        try:
            # Mark Ingestion Processing
            self.repository.mark_ingestion_started(
                relative_path=relative_path,
                source=file_name,
                last_write_time_utc=last_write_time_utc,
                length=file_length,
                fingerprint=fingerprint
            )
            # Delete any previous chunks
            self.repository.delete_documents_for_file(relative_path)

            # 1. Parse all documents from stream (raw text & OCR)
            parsed_docs: List[IngestedDocument] = []
            async for doc in parser.parse_stream_async(file_path, file_name):
                if doc.page_content.strip():
                    parsed_docs.append(doc)

            if not parsed_docs:
                logger.warning(f"No content extracted from file: {file_name}")

            # 2. Convert extracted text to Markdown (in-memory, not persisted to disk)
            #    Bỏ qua các doc bypass splitter (tabular, slide, vision) vì đã có định dạng riêng
            for doc in parsed_docs:
                if not self._should_bypass_splitter(doc.metadata, is_tabular):
                    doc.page_content = self._convert_to_markdown(doc.page_content)
            logger.info(f"MarkItDown conversion applied for non-bypass documents in: {file_name}")

            # 3. Apply Vietnamese Normalization on the full Markdown (or raw text for bypass docs)
            #    This runs: Unicode NFC -> Strip excess spaces -> Normalize newlines -> Expand acronyms -> Vietnamese clean (punctuation, zero-width, tone marks)
            for doc in parsed_docs:
                doc.page_content = VietnameseNormalizer.normalize(doc.page_content, expand_acronyms=True)

            # 4. Chunk documents using SemanticChunker or bypass logic
            all_chunks: List[IngestedDocument] = []
            for doc in parsed_docs:
                if self._should_bypass_splitter(doc.metadata, is_tabular):
                    all_chunks.append(doc)
                else:
                    chunks = SemanticChunker.split_documents(
                        [doc],
                        min_tokens=settings.ingestion_chunk_tokens_min,
                        max_tokens=settings.ingestion_chunk_tokens_max,
                        overlap_tokens=settings.ingestion_chunk_overlap_tokens
                    )
                    all_chunks.extend(chunks)

            total_chunks = len(all_chunks)

            # 5. Batch Embed and Upsert with Flat Metadata Schema
            batch_size = settings.ingestion_batch_size
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

            for global_chunk_index in range(0, total_chunks, batch_size):
                batch = all_chunks[global_chunk_index:global_chunk_index + batch_size]
                texts = [c.page_content for c in batch]

                embeddings = await self.embedding_service.embed_texts(texts)

                ids = []
                metadatas = []

                for idx_in_batch, chunk in enumerate(batch):
                    chunk_idx = global_chunk_index + idx_in_batch
                    chunk_id = TextSplitter.generate_chunk_id(
                        relative_path=relative_path,
                        last_write_time_utc=last_write_time_utc,
                        length=file_length,
                        index=chunk_idx
                    )
                    
                    # Flat Metadata Schema
                    chunk.metadata["relative_path"] = relative_path
                    chunk.metadata["chunkIndex"] = chunk_idx
                    chunk.metadata["totalChunks"] = total_chunks
                    chunk.metadata["source"] = file_name
                    chunk.metadata["sourceFile"] = file_name
                    chunk.metadata["version"] = 1
                    chunk.metadata["uploadedAt"] = custom_metadata.get("creationTime", now_iso) if custom_metadata else now_iso

                    if custom_metadata:
                        chunk.metadata["documentId"] = custom_metadata.get("backend_document_id")
                        chunk.metadata["backend_document_id"] = custom_metadata.get("backend_document_id")
                        chunk.metadata["title"] = custom_metadata.get("documentName", file_name)
                        chunk.metadata["documentName"] = custom_metadata.get("documentName", file_name)
                        chunk.metadata["category"] = custom_metadata.get("category", "")
                        chunk.metadata["ownerDepartment"] = custom_metadata.get("ownerDepartment", "")
                        chunk.metadata["description"] = custom_metadata.get("description", "")
                        chunk.metadata["tags"] = custom_metadata.get("tags", [])
                        chunk.metadata["effectiveDate"] = custom_metadata.get("effectiveDate")
                        chunk.metadata["expirationDate"] = custom_metadata.get("expirationDate")
                        chunk.metadata["accessScope"] = custom_metadata.get("accessScope", "Public")
                        chunk.metadata["allowedRoles"] = custom_metadata.get("allowedRoles", [])
                        chunk.metadata["uploadedBy"] = custom_metadata.get("uploadedBy", "")
                        if "storage_key" in custom_metadata:
                            chunk.metadata["storage_key"] = custom_metadata["storage_key"]

                    ids.append(chunk_id)
                    metadatas.append(chunk.metadata)

                self.repository.upsert_documents(
                    ids=ids,
                    documents=texts,
                    metadatas=metadatas,
                    embeddings=embeddings
                )

            # Mark Completed in IngestionFiles and RagDocuments
            self.repository.mark_ingestion_completed(relative_path, total_chunks)
            
            doc_id = custom_metadata.get("backend_document_id") if custom_metadata else None
            if doc_id:
                try:
                    self.repository.update_rag_document_status(int(doc_id), "Completed", total_chunks)
                except Exception as db_ex:
                    logger.error(f"Failed to update RagDocuments status for doc ID {doc_id}: {db_ex}")

            logger.info(f"Ingestion completed for file: {file_name} ({total_chunks} chunks)")
            return True, total_chunks

        except Exception as ex:
            logger.error(f"Ingestion failed for file '{file_name}': {ex}", exc_info=True)
            self.repository.mark_ingestion_failed(relative_path, str(ex))
            
            doc_id = custom_metadata.get("backend_document_id") if custom_metadata else None
            if doc_id:
                try:
                    self.repository.update_rag_document_status(int(doc_id), "Failed", 0, str(ex))
                except Exception as db_ex:
                    logger.error(f"Failed to update RagDocuments error status for doc ID {doc_id}: {db_ex}")
            return False, 0
