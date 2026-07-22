import json
import logging
import os
import tempfile
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Header
from typing import Optional
from app.models.api_models import (
    AddDocumentsRequest, AddDocumentsResponse, 
    SearchRequest, SearchResponse,
    CreateDocumentMetadataRequest, UpdateDocumentStatusRequest
)
from app.data.sql_repository import SqlDocumentRepository
from app.services.tei_embedding import TeiEmbeddingService
from app.ingestion.ingestion_service import IngestionService
from app.dependencies import get_repository, get_embedding_service, get_ingestion_service

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/add", response_model=AddDocumentsResponse)
async def add_documents(
    request: AddDocumentsRequest,
    repository: SqlDocumentRepository = Depends(get_repository),
    embedding_service: TeiEmbeddingService = Depends(get_embedding_service)
):
    if len(request.ids) != len(request.documents):
        raise HTTPException(status_code=400, detail="ids count must match documents count.")

    if request.metadatas is not None and len(request.metadatas) != len(request.documents):
        raise HTTPException(status_code=400, detail="metadatas count must match documents count when provided.")

    try:
        # Embed the texts using TEI
        embeddings = await embedding_service.embed_texts(request.documents)
        
        # Upsert
        metadatas = request.metadatas if request.metadatas is not None else [{} for _ in request.documents]
        repository.upsert_documents(
            ids=request.ids,
            documents=request.documents,
            metadatas=metadatas,
            embeddings=embeddings
        )
        return AddDocumentsResponse(status="success", count=len(request.documents))
    except Exception as ex:
        logger.error(f"Error in /db/add: {ex}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(ex))

@router.post("/search", response_model=SearchResponse)
async def search_documents(
    request: SearchRequest,
    x_user_roles: Optional[str] = Header(None, alias="X-User-Roles"),
    repository: SqlDocumentRepository = Depends(get_repository),
    embedding_service: TeiEmbeddingService = Depends(get_embedding_service)
):
    try:
        # Embed query text
        query_embedding, cache_hit = await embedding_service.embed_query_cached(request.query)

        # Run vector database search
        # Prefer user_roles from request body if present, else fall back to header
        roles = request.user_roles or x_user_roles

        response = repository.search(
            query=request.query,
            query_embedding=query_embedding,
            top_k=request.top_k,
            content_kind=request.content_kind,
            user_roles=roles
        )
        return SearchResponse(**response)
    except Exception as ex:
        logger.error(f"Error in /db/search: {ex}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(ex))

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    metadata: str = Form(...),
    ingestion_service: IngestionService = Depends(get_ingestion_service)
):
    if not metadata:
        raise HTTPException(status_code=400, detail="Metadata is required.")

    # Decode RFC 2047 MIME encoded filename if present (due to C# HttpClient encoding Vietnamese characters)
    from email.header import decode_header
    filename = file.filename
    try:
        decoded_parts = decode_header(filename)
        decoded_filename = ""
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                decoded_filename += part.decode(encoding or 'utf-8', errors='replace')
            else:
                decoded_filename += part
        if decoded_filename:
            filename = decoded_filename
    except Exception as mime_ex:
        logger.warning(f"Failed to decode MIME filename {file.filename}: {mime_ex}")

    # Parse custom metadata JSON
    try:
        custom_metadata = json.loads(metadata)
    except Exception as ex:
        logger.error(f"Failed to deserialize upload metadata: {ex}")
        raise HTTPException(status_code=400, detail=f"Invalid metadata format: {ex}")

    # Read chunks of the uploaded file
    content = await file.read()
    if not content or len(content) == 0:
        raise HTTPException(status_code=400, detail="No file uploaded or file is empty.")

    # Write file stream to temporary location for ingestion parsing
    fd, temp_file_path = tempfile.mkstemp()
    try:
        with os.fdopen(fd, 'wb') as temp_file:
            temp_file.write(content)
        
        success, chunk_count = await ingestion_service.ingest_file(
            file_path=temp_file_path,
            file_name=filename,
            custom_metadata=custom_metadata
        )

        if success:
            return {"status": "success", "message": f"Successfully ingested {filename}.", "chunkCount": chunk_count}
        else:
            raise HTTPException(status_code=500, detail="Failed to ingest document chunks.")
    except Exception as ex:
        logger.error(f"Error occurred during document upload processing: {ex}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(ex))
    finally:
        # Delete temporary file immediately after ingestion finishes
        try:
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
        except Exception as ex:
            logger.warning(f"Failed to delete temporary file {temp_file_path}: {ex}")

@router.post("/documents")
async def create_document(
    request: CreateDocumentMetadataRequest,
    repository: SqlDocumentRepository = Depends(get_repository)
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
            allowed_roles=request.allowed_roles
        )
        return {"status": "success", "id": doc_id}
    except Exception as ex:
        logger.error(f"Error in POST /db/documents: {ex}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(ex))

@router.get("/documents")
async def get_documents_list(
    repository: SqlDocumentRepository = Depends(get_repository)
):
    try:
        docs = repository.get_rag_documents_list()
        return docs
    except Exception as ex:
        logger.error(f"Error in GET /db/documents: {ex}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(ex))

@router.get("/documents/{id}")
async def get_document(
    id: int,
    repository: SqlDocumentRepository = Depends(get_repository)
):
    try:
        doc = repository.get_rag_document(id)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found.")
        return doc
    except HTTPException:
        raise
    except Exception as ex:
        logger.error(f"Error in GET /db/documents/{id}: {ex}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(ex))

@router.get("/documents/{id}/roles")
async def get_document_roles(
    id: int,
    repository: SqlDocumentRepository = Depends(get_repository)
):
    try:
        roles = repository.get_rag_document_roles(id)
        return roles
    except Exception as ex:
        logger.error(f"Error in GET /db/documents/{id}/roles: {ex}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(ex))

@router.put("/documents/{id}/status")
async def update_document_status(
    id: int,
    request: UpdateDocumentStatusRequest,
    repository: SqlDocumentRepository = Depends(get_repository)
):
    try:
        repository.update_rag_document_status(id, request.status, request.chunk_count, request.error)
        return {"status": "success"}
    except Exception as ex:
        logger.error(f"Error in PUT /db/documents/{id}/status: {ex}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(ex))

@router.delete("/documents/{backend_id}")
def delete_document(
    backend_id: int,
    repository: SqlDocumentRepository = Depends(get_repository)
):
    try:
        file_path = repository.delete_rag_document(backend_id)
        if not file_path:
            repository.delete_documents_by_backend_id(backend_id)
            return {"status": "success", "message": f"Successfully deleted chunks for document ID {backend_id}.", "filePath": None}
        return {"status": "success", "message": f"Successfully deleted document and chunks for ID {backend_id}.", "filePath": file_path}
    except Exception as ex:
        logger.error(f"Error deleting document ID {backend_id}: {ex}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(ex))
