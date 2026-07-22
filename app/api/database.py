import json
import logging
import os
import tempfile
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Header
from typing import Optional
from app.models.api_models import (
    AddDocumentsRequest, AddDocumentsResponse, 
    SearchRequest, SearchResponse
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
            file_name=file.filename,
            custom_metadata=custom_metadata
        )

        if success:
            return {"status": "success", "message": f"Successfully ingested {file.filename}.", "chunkCount": chunk_count}
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

@router.delete("/documents/{backend_id}")
def delete_document(
    backend_id: int,
    repository: SqlDocumentRepository = Depends(get_repository)
):
    try:
        repository.delete_documents_by_backend_id(backend_id)
        return {"status": "success", "message": f"Successfully deleted chunks for document ID {backend_id}."}
    except Exception as ex:
        logger.error(f"Error deleting chunks for document ID {backend_id}: {ex}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(ex))
