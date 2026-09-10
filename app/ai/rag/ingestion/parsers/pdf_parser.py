import fitz  # PyMuPDF
import logging
from typing import List
from app.ai.rag.ingestion.parsers.base import BaseDocumentParser, IngestedDocument
from app.ai.rag.text.text_cleaner import TextArtifactCleaner
from app.ai.rag.ingestion.procedure_extractor import ProcedureBlockExtractor
from app.ai.vision.ocr_service import TesseractOcrService
from app.shared.utils.action_classifier import ActionKindClassifier

logger = logging.getLogger(__name__)

class PdfParser(BaseDocumentParser):
    def __init__(self, ocr_service: TesseractOcrService):
        self.ocr_service = ocr_service

    def can_parse(self, extension: str) -> bool:
        return extension.lower() == ".pdf"

    async def parse_async(self, file_path: str, file_name: str) -> List[IngestedDocument]:
        emitted_docs = []
        doc = fitz.open(file_path)

        try:
            logger.info(f"[PDF] Parsing '{file_name}' ({len(doc)} pages)...")
            for page_num in range(len(doc)):
                page = doc[page_num]
                page_index = page_num + 1
                text = page.get_text("text")

                words = page.get_text("words")
                if len(words) < 10 or not text.strip():
                    logger.info(f"[PDF] Page {page_index} is scanned. Running OCR...")
                    pix = page.get_pixmap(dpi=150)
                    image_bytes = pix.tobytes("png")
                    ocr_text = await self.ocr_service.extract_text(image_bytes)
                    if ocr_text and ocr_text.strip():
                        text = ocr_text
                    else:
                        continue

                cleaned_text = TextArtifactCleaner.collapse_icon_gaps(text)
                if not cleaned_text or not cleaned_text.strip():
                    continue

                page_title = None
                lines = cleaned_text.splitlines()
                for line in lines:
                    trimmed = line.strip()
                    if trimmed and not ProcedureBlockExtractor.is_step_line(trimmed):
                        page_title = trimmed
                        break

                page_action_kind = ActionKindClassifier.determine_action_kind(page_title) if page_title else None
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
