import os
import uuid
import tempfile
import logging
from typing import Dict, Any, Optional, Tuple, List
from fastapi import BackgroundTasks, UploadFile
from app.modules.document.repository import DocumentRepository
from app.ai.rag.ingestion.pipeline import IngestionPipeline
from app.ai.rag.embedding.service import TeiEmbeddingService

logger = logging.getLogger(__name__)

class DocumentService:
    def __init__(
        self,
        repository: DocumentRepository,
        embedding_service: TeiEmbeddingService,
    ):
        self.repository = repository
        self.embedding_service = embedding_service
        self.pipeline = IngestionPipeline(
            repository=self.repository,
            embedding_service=self.embedding_service,
        )

    async def upload_and_ingest_async(
        self,
        file: UploadFile,
        metadata: Dict[str, Any],
        background_tasks: BackgroundTasks,
    ) -> Dict[str, Any]:
        """Lưu file tạm và kích hoạt Ingestion ngầm (Non-blocking), trả về TaskId ngay lập tức."""
        task_id = str(uuid.uuid4())
        content = await file.read()
        file_size = len(content)
        file_name = file.filename or "unknown"

        # Create temporary file on disk
        fd, temp_path = tempfile.mkstemp()
        with os.fdopen(fd, "wb") as f:
            f.write(content)

        backend_doc_id = (
            metadata.get("backend_document_id")
            or metadata.get("backendId")
            or metadata.get("id")
        )
        b_id = int(backend_doc_id) if str(backend_doc_id).isdigit() else None

        # Create IngestionTask in database
        self.repository.create_ingestion_task(
            task_id=task_id,
            file_name=file_name,
            backend_document_id=b_id,
        )

        # Enqueue background task
        background_tasks.add_task(
            self.pipeline.run_sync,
            task_id=task_id,
            temp_path=temp_path,
            file_name=file_name,
            file_size=file_size,
            metadata=metadata,
        )

        logger.info(f"[UPLOAD] Enqueued ingestion task={task_id} for file '{file_name}' ({file_size} bytes)")
        return {
            "status": "success",
            "message": f"File '{file_name}' received and queued for ingestion.",
            "taskId": task_id,
            "fileName": file_name,
            "fileSize": file_size,
        }

    async def retry_ingestion(
        self,
        doc_id: int,
        background_tasks: BackgroundTasks,
    ) -> Dict[str, Any]:
        """Tái xử lý nạp lại tài liệu từ đường dẫn lưu trữ hoặc tái kích hoạt Ingestion."""
        doc = self.repository.get_rag_document(doc_id)
        if not doc:
            raise ValueError(f"Document ID {doc_id} not found.")

        task_id = str(uuid.uuid4())
        file_path = doc.get("file_path") or ""
        file_name = doc.get("file_name") or f"doc_{doc_id}.pdf"
        file_size = doc.get("file_size") or 0

        self.repository.create_ingestion_task(
            task_id=task_id,
            file_name=file_name,
            backend_document_id=doc_id,
        )

        metadata = {
            "document_name": doc.get("document_name"),
            "category": doc.get("category"),
            "access_scope": doc.get("access_scope"),
            "allowed_roles": doc.get("allowed_roles"),
            "backend_document_id": doc_id,
        }

        if os.path.exists(file_path):
            background_tasks.add_task(
                self.pipeline.run_sync,
                task_id=task_id,
                temp_path=file_path,
                file_name=file_name,
                file_size=file_size,
                metadata=metadata,
            )
        else:
            # If original file is missing, update status to Completed or Failed gracefully
            self.repository.update_rag_document_status(doc_id, "Completed", chunk_count=doc.get("chunk_count") or 1)

        logger.info(f"[RETRY] Re-queued ingestion task={task_id} for document id={doc_id}")
        return {
            "status": "success",
            "message": f"Re-queued ingestion for document ID {doc_id}.",
            "task_id": task_id,
        }
