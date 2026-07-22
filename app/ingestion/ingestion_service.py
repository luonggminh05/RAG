import datetime
import hashlib
import logging
import os
from typing import List, Dict, Any, Optional
from app.config import settings
from app.ingestion.text_splitter import TextSplitter, IngestedDocument
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

    async def ingest_file(
        self,
        file_path: str,
        file_name: str,
        custom_metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
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

        global_chunk_index = 0
        doc_count = 0

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

            # Parse the stream of pages/paragraphs
            async for doc in parser.parse_stream_async(file_path, file_name):
                doc_count += 1
                
                # Split text
                if self._should_bypass_splitter(doc.metadata, is_tabular):
                    chunks = [doc]
                else:
                    chunks = TextSplitter.split_documents(
                        [doc],
                        settings.ingestion_chunk_size,
                        settings.ingestion_chunk_overlap
                    )

                if not chunks:
                    continue

                # Batch embed and insert
                batch_size = settings.ingestion_batch_size
                for offset in range(0, len(chunks), batch_size):
                    batch = chunks[offset:offset + batch_size]
                    texts = [c.page_content for c in batch]

                    # Embed
                    embeddings = await self.embedding_service.embed_texts(texts)

                    ids = []
                    metadatas = []

                    for idx, chunk in enumerate(batch):
                        chunk_id = TextSplitter.generate_chunk_id(
                            relative_path=relative_path,
                            last_write_time_utc=last_write_time_utc,
                            length=file_length,
                            index=global_chunk_index
                        )
                        
                        # Populate system metadata
                        chunk.metadata["relative_path"] = relative_path
                        chunk.metadata["chunk_index"] = global_chunk_index

                        # Populate custom metadata from form-data if provided
                        if custom_metadata:
                            chunk.metadata["documentName"] = custom_metadata.get("documentName", "")
                            chunk.metadata["category"] = custom_metadata.get("category", "")
                            chunk.metadata["ownerDepartment"] = custom_metadata.get("ownerDepartment", "")
                            chunk.metadata["description"] = custom_metadata.get("description", "")
                            chunk.metadata["tags"] = custom_metadata.get("tags", [])
                            chunk.metadata["effectiveDate"] = custom_metadata.get("effectiveDate")
                            chunk.metadata["expirationDate"] = custom_metadata.get("expirationDate")
                            chunk.metadata["accessScope"] = custom_metadata.get("accessScope", "Public")
                            chunk.metadata["allowedRoles"] = custom_metadata.get("allowedRoles", [])
                            if "backend_document_id" in custom_metadata:
                                chunk.metadata["backend_document_id"] = custom_metadata["backend_document_id"]
                            if "storage_key" in custom_metadata:
                                chunk.metadata["storage_key"] = custom_metadata["storage_key"]

                        ids.append(chunk_id)
                        metadatas.append(chunk.metadata)
                        global_chunk_index += 1

                    self.repository.upsert_documents(
                        ids=ids,
                        documents=texts,
                        metadatas=metadatas,
                        embeddings=embeddings
                    )

            if doc_count == 0:
                logger.warning(f"No content extracted from file: {file_name}")

            # Mark Completed
            self.repository.mark_ingestion_completed(relative_path, global_chunk_index)
            logger.info(f"Ingestion completed for file: {file_name} ({global_chunk_index} chunks)")
            return True, global_chunk_index

        except Exception as ex:
            logger.error(f"Ingestion failed for file '{file_name}': {ex}", exc_info=True)
            self.repository.mark_ingestion_failed(relative_path, str(ex))
            return False, 0
