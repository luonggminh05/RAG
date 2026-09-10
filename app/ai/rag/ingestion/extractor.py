import os
import logging
from typing import List, Dict, Any, Optional
from app.ai.rag.ingestion.parsers import (
    BaseDocumentParser,
    DocumentParserRegistry,
    IngestedDocument,
    TextParser,
    PdfParser,
    WordParser,
    PowerPointParser,
    TabularParser,
    ImageParser,
)
from app.ai.vision.ocr_service import TesseractOcrService
from app.ai.vision.vision_service import VisionService

logger = logging.getLogger(__name__)

class FileTextExtractor:
    """Điều phối giải mã nội dung từ các định dạng file đĩa sang IngestedDocument."""

    def __init__(
        self,
        ocr_service: Optional[TesseractOcrService] = None,
        vision_service: Optional[VisionService] = None,
    ):
        self.ocr_service = ocr_service or TesseractOcrService()
        self.vision_service = vision_service or VisionService()

        self.text_parser = TextParser()
        self.pdf_parser = PdfParser(ocr_service=self.ocr_service)
        self.word_parser = WordParser()
        self.pptx_parser = PowerPointParser(
            ocr_service=self.ocr_service, vision_service=self.vision_service
        )
        self.tabular_parser = TabularParser()
        self.image_parser = ImageParser(
            ocr_service=self.ocr_service, vision_service=self.vision_service
        )

        self.registry = DocumentParserRegistry([
            self.text_parser,
            self.pdf_parser,
            self.word_parser,
            self.pptx_parser,
            self.tabular_parser,
            self.image_parser,
        ])

    async def extract(self, file_path: str, file_name: str) -> List[IngestedDocument]:
        ext = os.path.splitext(file_name)[1].lower()
        try:
            parser = self.registry.get_parser(ext)
            return await parser.parse_async(file_path, file_name)
        except Exception as ex:
            logger.error(f"[EXTRACT] Failed to parse '{file_name}' with ext '{ext}': {ex}")
            # Fallback plain text read
            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                return [IngestedDocument(page_content=content, metadata={"source": file_name, "type": "fallback_text"})]
            except Exception:
                return []
