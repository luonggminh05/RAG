import json
import logging
from typing import Optional
from email.header import decode_header
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Header, BackgroundTasks
from app.modules.document.api.v1.schemas import (
    AddDocumentsRequest, AddDocumentsResponse,
    SearchRequest, SearchResponse,
    CreateDocumentMetadataRequest, UpdateDocumentMetadataRequest,
    UpdateDocumentStatusRequest, IngestionTaskResponse
)
from app.modules.document.repository import DocumentRepository
from app.modules.document.service import DocumentService
from app.ai.rag.embedding.service import TeiEmbeddingService
from app.routers.dependencies import get_document_repository, get_embedding_service, get_document_service

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/add", response_model=AddDocumentsResponse)
async def add_documents(
    request: AddDocumentsRequest,
    repository: DocumentRepository = Depends(get_document_repository),
    embedding_service: TeiEmbeddingService = Depends(get_embedding_service),
):
    if len(request.ids) != len(request.documents):
        raise HTTPException(status_code=400, detail="ids count must match documents count.")
    if request.metadatas is not None and len(request.metadatas) != len(request.documents):
        raise HTTPException(status_code=400, detail="metadatas count must match documents count.")

    try:
        embeddings = await embedding_service.embed_texts(request.documents)
        metadatas = request.metadatas if request.metadatas is not None else [{} for _ in request.documents]
        repository.upsert_documents(
            ids=request.ids,
            documents=request.documents,
            metadatas=metadatas,
            embeddings=embeddings,
        )
        return AddDocumentsResponse(status="success", count=len(request.documents))
    except Exception as ex:
        logger.error(f"Error in /add: {ex}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(ex))


@router.post("/search", response_model=SearchResponse)
async def search_documents(
    request: SearchRequest,
    x_user_roles: Optional[str] = Header(None, alias="X-User-Roles"),
    x_user_department: Optional[str] = Header(None, alias="X-User-Department"),
    repository: DocumentRepository = Depends(get_document_repository),
    embedding_service: TeiEmbeddingService = Depends(get_embedding_service),
):
    try:
        query_embedding, _ = await embedding_service.embed_query_cached(request.query)
        roles = request.user_roles or x_user_roles
        dept = request.user_department or x_user_department

        response = repository.search(
            query=request.query,
            query_embedding=query_embedding,
            top_k=request.top_k,
            content_kind=request.content_kind,
            user_roles=roles,
            user_department=dept,
        )
        return SearchResponse(**response)
    except Exception as ex:
        logger.error(f"Error in /search: {ex}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(ex))


@router.post("/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    metadata: str = Form(...),
    enable_ocr: Optional[bool] = Form(None),
    enable_vision_caption: Optional[bool] = Form(None),
    document_service: DocumentService = Depends(get_document_service),
):
    if not metadata:
        raise HTTPException(status_code=400, detail="Metadata is required.")

    # MIME Decode filename
    filename = file.filename or "unknown"
    try:
        decoded_parts = decode_header(filename)
        decoded_filename = ""
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                decoded_filename += part.decode(encoding or 'utf-8', errors='replace')
            else:
                decoded_filename += part
        if decoded_filename:
            file.filename = decoded_filename
    except Exception:
        pass

    try:
        custom_metadata = json.loads(metadata) if isinstance(metadata, str) else metadata
    except Exception as ex:
        raise HTTPException(status_code=400, detail=f"Invalid metadata JSON: {ex}")

    if enable_ocr is not None:
        custom_metadata["enable_ocr"] = enable_ocr
    if enable_vision_caption is not None:
        custom_metadata["enable_vision_caption"] = enable_vision_caption

    return await document_service.upload_and_ingest_async(
        file=file,
        metadata=custom_metadata,
        background_tasks=background_tasks,
    )


@router.get("/tasks/{task_id}")
async def get_task_status(
    task_id: str,
    repository: DocumentRepository = Depends(get_document_repository),
):
    task = repository.get_ingestion_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found.")
    return task


@router.post("/documents")
async def create_document(
    request: CreateDocumentMetadataRequest,
    repository: DocumentRepository = Depends(get_document_repository),
):
    try:
        doc_id = repository.create_rag_document(
            document_name=request.document_name,
            file_name=request.file_name,
            file_path=request.file_path,
            file_size=request.file_size,
            category=request.category,
            owner_department=request.owner_department,
            description=request.description,
            tags=request.tags,
            access_scope=request.access_scope,
            effective_date=request.effective_date,
            expiration_date=request.expiration_date,
            uploaded_by=request.uploaded_by,
            tenant_id=request.tenant_id,
            allowed_roles=request.allowed_roles,
        )
        return {"status": "success", "id": doc_id}
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))


@router.get("/documents")
async def get_documents_list(
    repository: DocumentRepository = Depends(get_document_repository),
):
    return repository.get_rag_documents_list()


@router.get("/documents/{id}")
async def get_document(
    id: int,
    repository: DocumentRepository = Depends(get_document_repository),
):
    doc = repository.get_rag_document(id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    return doc


@router.get("/documents/{id}/roles")
async def get_document_roles(
    id: int,
    repository: DocumentRepository = Depends(get_document_repository),
):
    return repository.get_rag_document_roles(id)


@router.put("/documents/{id}/status")
async def update_document_status(
    id: int,
    request: UpdateDocumentStatusRequest,
    repository: DocumentRepository = Depends(get_document_repository),
):
    repository.update_rag_document_status(id, request.status, request.chunk_count, request.error)
    return {"status": "success"}


@router.put("/documents/{id}")
@router.post("/documents/{id}")
async def update_document_metadata(
    id: int,
    request: UpdateDocumentMetadataRequest,
    repository: DocumentRepository = Depends(get_document_repository),
):
    repository.update_rag_document(
        doc_id=id,
        document_name=request.document_name,
        category=request.category,
        access_scope=request.access_scope,
        allowed_roles=request.allowed_roles,
    )
    return {"status": "success"}


@router.delete("/documents/{backend_id}")
def delete_document(
    backend_id: int,
    repository: DocumentRepository = Depends(get_document_repository),
):
    file_path = repository.delete_rag_document(backend_id)
    repository.delete_documents_by_backend_id(backend_id)
    return {"status": "success", "message": f"Successfully deleted document ID {backend_id}.", "filePath": file_path}


@router.post("/documents/{id}/retry")
async def retry_document_ingestion(
    id: int,
    background_tasks: BackgroundTasks,
    document_service: DocumentService = Depends(get_document_service),
):
    try:
        return await document_service.retry_ingestion(doc_id=id, background_tasks=background_tasks)
    except Exception as ex:
        logger.error(f"Error retrying document ID {id}: {ex}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(ex))
