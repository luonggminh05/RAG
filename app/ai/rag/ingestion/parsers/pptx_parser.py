import io
import re
import logging
import zipfile
from typing import List, Dict, Any, AsyncGenerator, Optional
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

from app.core.config import settings
from app.ai.rag.ingestion.parsers.base import BaseDocumentParser, IngestedDocument
from app.ai.vision.ocr_service import TesseractOcrService
from app.ai.vision.vision_service import VisionService
from app.ai.vision.image_classifier import ImageContentClassifier, ImageRole, VisionCaptionQuality
from app.ai.rag.ingestion.procedure_extractor import ProcedureBlockExtractor
from app.ai.vision.image_utils import ImageUtilities
from app.shared.utils.action_classifier import ActionKindClassifier

logger = logging.getLogger(__name__)

class PowerPointParser(BaseDocumentParser):
    def __init__(self, ocr_service: TesseractOcrService, vision_service: VisionService):
        self.ocr_service = ocr_service
        self.vision_service = vision_service

    def can_parse(self, extension: str) -> bool:
        return extension.lower() in [".pptx", ".ppt"]

    async def parse_async(self, file_path: str, file_name: str) -> List[IngestedDocument]:
        docs = []
        try:
            async for doc in self.parse_stream(file_path, file_name):
                docs.append(doc)
        except Exception as ex:
            logger.warning(f"[PPTX] OpenXML pptx parsing failed for {file_name}. Trying zip fallback: {ex}")
            docs = self._parse_fallback(file_path, file_name)
        return docs

    async def parse_stream(self, file_path: str, file_name: str) -> AsyncGenerator[IngestedDocument, None]:
        prs = Presentation(file_path)

        for slide_index, slide in enumerate(prs.slides, start=1):
            slide_title = self._detect_slide_title(slide)
            action_kind = ActionKindClassifier.determine_action_kind(slide_title) if slide_title else None

            instruction_blocks = []
            image_chunks = []
            image_idx = 0

            async def process_shape(shape):
                nonlocal image_idx
                if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
                    for child in shape.shapes:
                        await process_shape(child)
                    return

                if shape.has_table:
                    for row in shape.table.rows:
                        row_texts = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                        if row_texts:
                            self._add_instruction_text(instruction_blocks, " | ".join(row_texts), action_kind)
                    return

                if shape.has_text_frame and shape.text_frame.text.strip():
                    self._add_instruction_text(instruction_blocks, shape.text_frame.text, action_kind)
                    return

                if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                    image_bytes = shape.image.blob
                    dims = ImageUtilities.try_get_dimensions(image_bytes)
                    if not dims:
                        return
                    width, height = dims
                    image_idx += 1
                    ocr_text = await self.ocr_service.extract_text(image_bytes)
                    role = ImageContentClassifier.classify(
                        width, height, ocr_text,
                        getattr(settings, "ingestion_min_vision_image_width", 100),
                        getattr(settings, "ingestion_min_vision_image_height", 100)
                    )

                    if role == ImageRole.InlineIcon:
                        marker = ImageContentClassifier.build_inline_marker(ocr_text)
                        if marker:
                            self._add_instruction_text(instruction_blocks, marker, action_kind)
                    elif role == ImageRole.UiScreenshot:
                        meta = {
                            "source": file_name,
                            "slide": slide_index,
                            "type": "pptx_image",
                            "content_kind": "image_ui_description",
                            "image_role": "Screenshot",
                            "width": width,
                            "height": height
                        }
                        if slide_title:
                            meta["slide_title"] = slide_title
                        if action_kind:
                            meta["action_kind"] = action_kind

                        caption = await self.vision_service.generate_caption(image_bytes, meta, ocr_text)
                        useful_caption = caption if VisionCaptionQuality.is_useful(caption, ocr_text) else None

                        if useful_caption:
                            header = f"[SLIDE {slide_index}: {slide_title}]\n[ẢNH GIAO DIỆN]" if slide_title else f"[SLIDE {slide_index}]\n[ẢNH GIAO DIỆN]"
                            image_chunks.append(IngestedDocument(
                                page_content=f"{header}\n{useful_caption}",
                                metadata=meta
                            ))

            for shape in slide.shapes:
                await process_shape(shape)

            for b in instruction_blocks:
                header = f"[SLIDE {slide_index}: {slide_title}]\n[VĂN BẢN HƯỚNG DẪN]" if slide_title else f"[SLIDE {slide_index}]\n[VĂN BẢN HƯỚNG DẪN]"
                meta = {
                    "source": file_name,
                    "slide": slide_index,
                    "type": "pptx_slide",
                    "content_kind": "instruction_text",
                    "instruction_role": b.instruction_role
                }
                if slide_title:
                    meta["slide_title"] = slide_title
                if b.action_kind:
                    meta["action_kind"] = b.action_kind
                if b.step_count > 0:
                    meta["step_count"] = b.step_count

                yield IngestedDocument(page_content=f"{header}\n{b.text}", metadata=meta)

            for ic in image_chunks:
                yield ic

    def _detect_slide_title(self, slide) -> Optional[str]:
        for shape in slide.shapes:
            if shape.has_text_frame and shape.text_frame.text.strip():
                txt = shape.text_frame.text.strip()
                if len(txt) <= 120 and not ProcedureBlockExtractor.is_step_line(txt):
                    return txt
        return None

    def _add_instruction_text(self, blocks, text: str, parent_action_kind: Optional[str]):
        extracted = ProcedureBlockExtractor.extract(text, parent_action_kind)
        blocks.extend(extracted)

    def _parse_fallback(self, file_path: str, file_name: str) -> List[IngestedDocument]:
        docs = []
        try:
            with zipfile.ZipFile(file_path, "r") as z:
                slide_files = [f for f in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml", f)]
                for sf in sorted(slide_files):
                    m = re.search(r"slide(\d+)\.xml", sf)
                    slide_num = int(m.group(1)) if m else 1
                    xml_content = z.read(sf).decode("utf-8", errors="replace")
                    texts = re.findall(r"<a:t[^>]*>(.*?)</a:t>", xml_content)
                    if texts:
                        combined = " ".join(texts).strip()
                        docs.append(IngestedDocument(
                            page_content=f"[SLIDE {slide_num}]\n{combined}",
                            metadata={"source": file_name, "slide": slide_num, "type": "pptx_fallback"}
                        ))
        except Exception as ex:
            logger.error(f"[PPTX] Fallback extraction failed for {file_name}: {ex}")
        return docs
