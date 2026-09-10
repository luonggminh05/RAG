from app.modules.document.repository import DocumentRepository
from app.modules.document.service import DocumentService
from app.modules.chat.repository import ChatRepository
from app.modules.chat.service import ChatService
from app.ai.rag.embedding.service import TeiEmbeddingService
from app.ai.vision.ocr_service import TesseractOcrService
from app.ai.vision.vision_service import VisionService
from app.ai.rag.reranker.factory import get_reranker
from app.ai.rag.retrieval.retriever import VectorRetriever

# Singletons
_document_repository = DocumentRepository()
_chat_repository = ChatRepository()
_embedding_service = TeiEmbeddingService()
_ocr_service = TesseractOcrService()
_vision_service = VisionService()
_reranker = get_reranker()
_vector_retriever = VectorRetriever(
    repository=_document_repository,
    embedding_service=_embedding_service,
    reranker=_reranker,
)
_document_service = DocumentService(
    repository=_document_repository,
    embedding_service=_embedding_service,
)
_chat_service = ChatService(
    repository=_chat_repository,
    retriever=_vector_retriever,
    vision_service=_vision_service,
)

def get_document_repository() -> DocumentRepository:
    return _document_repository

def get_chat_repository() -> ChatRepository:
    return _chat_repository

def get_embedding_service() -> TeiEmbeddingService:
    return _embedding_service

def get_ocr_service() -> TesseractOcrService:
    return _ocr_service

def get_vision_service() -> VisionService:
    return _vision_service

def get_vector_retriever() -> VectorRetriever:
    return _vector_retriever

def get_document_service() -> DocumentService:
    return _document_service

def get_chat_service() -> ChatService:
    return _chat_service

# Aliases for backwards compatibility with legacy Rag dependency imports
get_repository = get_document_repository
get_ingestion_service = get_document_service
repository = _document_repository
embedding_service = _embedding_service
ocr_service = _ocr_service
vision_service = _vision_service
ingestion_service = _document_service
