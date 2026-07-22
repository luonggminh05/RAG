import fitz  # PyMuPDF
import logging
from typing import List, Optional, Dict, Any
from app.ingestion.parsers.base import BaseDocumentParser
from app.ingestion.text_splitter import IngestedDocument
from app.ingestion.text_cleaner import TextArtifactCleaner
from app.ingestion.procedure_extractor import ProcedureBlockExtractor
from app.services.ocr_service import TesseractOcrService
from app.services.action_classifier import ActionKindClassifier

logger = logging.getLogger(__name__)

class PdfParser(BaseDocumentParser):
    def __init__(self, ocr_service: TesseractOcrService):
        self.ocr_service = ocr_service

    def can_parse(self, extension: str) -> bool:
        return extension.lower() == ".pdf"

    async def parse_async(self, file_path: str, file_name: str) -> List[IngestedDocument]:
        emitted_docs = []
        
        # Open PDF file using fitz
        doc = fitz.open(file_path)
        
        try:
            logger.info(f"Starting PDF parse for '{file_name}' ({len(doc)} pages)...")
            for page_num in range(len(doc)):
                page = doc[page_num]
                page_index = page_num + 1  # 1-based page number
                logger.info(f"Parsing PDF '{file_name}' page {page_index}/{len(doc)}...")

                text = page.get_text("text")

                # Heuristic for scanned pages: check if there's minimal text
                words = page.get_text("words")
                if len(words) < 10 or not text.strip():
                    logger.info(f"PDF page {page_index} is scanned (words: {len(words)}). Running OCR...")
                    # Run OCR on scanned PDF pages
                    pix = page.get_pixmap(dpi=150)
                    image_bytes = pix.tobytes("png")
                    ocr_text = await self.ocr_service.extract_text(image_bytes)
                    if ocr_text and ocr_text.strip():
                        text = ocr_text
                        logger.info(f"OCR completed successfully for page {page_index}.")
                    else:
                        logger.warning(f"No text extracted via OCR for page {page_index}.")
                        continue


                # Native PDF text extraction
                cleaned_text = TextArtifactCleaner.collapse_icon_gaps(text)
                if not cleaned_text or not cleaned_text.strip():
                    continue

                # Detect page title
                page_title = None
                lines = cleaned_text.splitlines()
                for line in lines:
                    trimmed = line.strip()
                    if trimmed and not ProcedureBlockExtractor.is_step_line(trimmed):
                        page_title = trimmed
                        break

                page_action_kind = ActionKindClassifier.determine_action_kind(page_title) if page_title else None

                # Extract procedure blocks (procedure_steps vs ui_details)
                blocks = ProcedureBlockExtractor.extract(cleaned_text, page_action_kind)
                for block in blocks:
                    page_content = (
                        f"[TRANG: {page_title}]\n[VĂN BẢN HƯỚNG DẪN]\n{block.text}"
                        if page_title else
                        f"[VĂN BẢN HƯỚNG DẪN]\n{block.text}"
                    )

                    metadata = {
                        "source": file_name,
                        "page": page_index,
                        "type": "pdf_text",
                        "content_kind": "instruction_text",
                        "instruction_role": block.instruction_role
                    }

                    if page_title:
                        metadata["page_title"] = page_title
                    
                    action_kind = block.action_kind or page_action_kind
                    if action_kind:
                        metadata["action_kind"] = action_kind

                    if block.step_count > 0:
                        metadata["step_count"] = block.step_count

                    emitted_docs.append(IngestedDocument(
                        page_content=page_content,
                        metadata=metadata
                    ))
        finally:
            doc.close()

        return emitted_docs
