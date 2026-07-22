from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class EmbedRequest(BaseModel):
    texts: List[str] = Field(default_factory=list)

class EmbedResponse(BaseModel):
    embeddings: List[List[float]]

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

    model_config = {
        "populate_by_name": True
    }

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
    citations: List[List[Citation]]

class HealthResponse(BaseModel):
    status: str
    message: str

class ChatImageInput(BaseModel):
    fileName: str
    contentType: str
    base64: str

class ChatRequest(BaseModel):
    message: str = ""
    images: List[ChatImageInput] = Field(default_factory=list)
    user_roles: Optional[str] = Field(default=None, alias="user_roles")
    conversation_id: Optional[str] = Field(default=None, alias="conversation_id")

    model_config = {
        "populate_by_name": True
    }

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

class UpdateDocumentStatusRequest(BaseModel):
    status: str
    chunk_count: int
    error: Optional[str] = None
