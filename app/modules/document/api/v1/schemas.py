from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class AddDocumentsRequest(BaseModel):
    documents: List[str]
    ids: List[str]
    metadatas: Optional[List[Dict[str, Any]]] = None

class AddDocumentsResponse(BaseModel):
    status: str
    count: int

class SearchRequest(BaseModel):
    query: str
    top_k: int = Field(default=5, alias="top_k")
    content_kind: Optional[str] = Field(default=None, alias="content_kind")
    user_roles: Optional[str] = Field(default=None, alias="user_roles")
    user_department: Optional[str] = Field(default=None, alias="user_department")

    model_config = {"populate_by_name": True}

class Citation(BaseModel):
    source: Optional[str] = None
    page: Optional[str] = None
    chunk_id: str
    score: float

class SearchResponse(BaseModel):
    ids: List[List[str]]
    documents: List[List[str]]
    metadatas: List[List[Dict[str, Any]]]
    distances: List[List[float]]
    citations: List[List[Dict[str, Any]]]

class CreateDocumentMetadataRequest(BaseModel):
    document_name: str
    file_name: str
    file_path: str
    file_size: int
    category: Optional[str] = None
    owner_department: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[str] = None
    access_scope: str = "Public"
    effective_date: Optional[str] = None
    expiration_date: Optional[str] = None
    uploaded_by: Optional[str] = None
    tenant_id: Optional[int] = None
    allowed_roles: List[str] = Field(default_factory=list)

class UpdateDocumentMetadataRequest(BaseModel):
    document_name: Optional[str] = None
    category: Optional[str] = None
    access_scope: Optional[str] = None
    allowed_roles: Optional[List[str]] = None

class UpdateDocumentStatusRequest(BaseModel):
    status: str
    chunk_count: int = 0
    error: Optional[str] = None

class IngestionTaskResponse(BaseModel):
    id: int
    task_id: str
    file_name: str
    status: str
    progress_percent: int
    chunk_count: int
    error_message: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
