from app.data.sql_repository import SqlDocumentRepository
from app.services.tei_embedding import TeiEmbeddingService
from app.services.ocr_service import TesseractOcrService
from app.services.vision_service import VisionService

from app.ingestion.parsers.base import DocumentParser
from app.ingestion.parsers.text_parser import TextParser
from app.ingestion.parsers.word_parser import WordParser
from app.ingestion.parsers.pdf_parser import PdfParser
from app.ingestion.parsers.pptx_parser import PowerPointParser
from app.ingestion.parsers.tabular_parser import TabularParser
from app.ingestion.parsers.image_parser import ImageParser
from app.ingestion.ingestion_service import IngestionService

# Singletons initialization
repository = SqlDocumentRepository()
embedding_service = TeiEmbeddingService()
ocr_service = TesseractOcrService()
vision_service = VisionService()

# Document Parsers
text_parser = TextParser()
word_parser = WordParser()
pdf_parser = PdfParser(ocr_service=ocr_service)
pptx_parser = PowerPointParser(ocr_service=ocr_service, vision_service=vision_service)
tabular_parser = TabularParser()
image_parser = ImageParser(ocr_service=ocr_service, vision_service=vision_service)

# Registered parser collection
parser_registry = DocumentParser([
    text_parser,
    word_parser,
    pdf_parser,
    pptx_parser,
    tabular_parser,
    image_parser
])

ingestion_service = IngestionService(
    parser_registry=parser_registry,
    embedding_service=embedding_service,
    repository=repository
)

# Dependency getters for FastAPI
def get_repository() -> SqlDocumentRepository:
    return repository

def get_embedding_service() -> TeiEmbeddingService:
    return embedding_service

def get_ingestion_service() -> IngestionService:
    return ingestion_service

def get_ocr_service() -> TesseractOcrService:
    return ocr_service

def get_vision_service() -> VisionService:
    return vision_service
