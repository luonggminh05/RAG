import logging
from typing import List
from app.ai.rag.ingestion.parsers.base import BaseDocumentParser, IngestedDocument
from app.ai.vision.ocr_service import TesseractOcrService
from app.ai.vision.vision_service import VisionService
from app.ai.vision.image_classifier import VisionCaptionQuality
from app.ai.vision.image_utils import ImageUtilities

logger = logging.getLogger(__name__)

class ImageParser(BaseDocumentParser):
    SupportedExtensions = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}

    def __init__(self, ocr_service: TesseractOcrService, vision_service: VisionService):
        self.ocr_service = ocr_service
        self.vision_service = vision_service

    def can_parse(self, extension: str) -> bool:
        return extension.lower() in self.SupportedExtensions

    async def parse_async(self, file_path: str, file_name: str) -> List[IngestedDocument]:
        docs = []
        try:
            with open(file_path, "rb") as f:
                image_bytes = f.read()
        except Exception as ex:
            logger.error(f"[IMAGE] Failed to read {file_name}: {ex}")
            return docs

        dims = ImageUtilities.try_get_dimensions(image_bytes)
        if not dims:
            logger.warning(f"[IMAGE] Skipping {file_name}: could not decode dimensions.")
            return docs

        width, height = dims
        metadata = {
            "source": file_name,
            "type": "image",
            "width": width,
            "height": height
        }

        ocr_text = await self.ocr_service.extract_text(image_bytes)
        caption = await self.vision_service.generate_caption(image_bytes, metadata, ocr_text)
        useful_caption = caption if VisionCaptionQuality.is_useful(caption, ocr_text) else None

        if not ocr_text and not useful_caption:
            logger.info(f"[IMAGE] {file_name} has no readable OCR text or vision caption. Skipping.")
            return docs

        content_parts = [f"Image dimensions: {width}x{height}px."]
        if ocr_text and ocr_text.strip():
            content_parts.append(f"OCR text: {ocr_text.strip()}")
        if useful_caption:
            content_parts.append(f"Vision caption: {useful_caption}")

        metadata["has_ocr_text"] = bool(ocr_text and ocr_text.strip())
        metadata["caption_source"] = "ocr+vision" if useful_caption else "ocr"

        docs.append(IngestedDocument(
            page_content="\n".join(content_parts),
            metadata=metadata
        ))

        return docs
