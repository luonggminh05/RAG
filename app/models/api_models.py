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
