import io
import re
import logging
import zipfile
from typing import List, Dict, Any, AsyncGenerator, Tuple, Optional
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE, PP_PLACEHOLDER

from app.config import settings
from app.ingestion.parsers.base import BaseDocumentParser, IngestedDocument
from app.services.ocr_service import TesseractOcrService
from app.services.vision_service import VisionService
from app.ingestion.image_classifier import ImageContentClassifier, ImageRole, VisionCaptionQuality
from app.ingestion.procedure_extractor import ProcedureBlockExtractor
from app.ingestion.image_utils import ImageUtilities

logger = logging.getLogger(__name__)

class PowerPointParser(BaseDocumentParser):
    def __init__(self, ocr_service: TesseractOcrService, vision_service: VisionService):
        self.ocr_service = ocr_service
        self.vision_service = vision_service

    def can_parse(self, extension: str) -> bool:
        return extension.lower() == ".pptx"

    async def parse_async(self, file_path: str, file_name: str) -> List[IngestedDocument]:
        docs = []
        try:
            # Attempt parsing using python-pptx
            async for doc in self.parse_stream(file_path, file_name):
                docs.append(doc)
        except Exception as ex:
            logger.warning(f"OpenXML pptx parsing failed for {file_name}. Trying zip fallback. Error: {ex}")
            docs = self._parse_fallback(file_path, file_name)
        return docs

    async def parse_stream(self, file_path: str, file_name: str) -> AsyncGenerator[IngestedDocument, None]:
        prs = Presentation(file_path)
        file_attempts = 0

        for slide_index, slide in enumerate(prs.slides, start=1):
            slide_attempts = 0
            
            # Detect title
            slide_title = self._detect_slide_title(slide)
            action_kind = None
            if slide_title:
                from app.services.action_classifier import ActionKindClassifier
                action_kind = ActionKindClassifier.determine_action_kind(slide_title)

            # Extract slide text & shapes
            instruction_blocks = []
            image_chunks = []
            image_idx = 0

            # Scan shapes recursively
            async def process_shape(shape):
                nonlocal image_idx, slide_attempts, file_attempts
                
                # Group shape
                if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
                    for child in shape.shapes:
                        await process_shape(child)
                    return

                # Table
                if shape.has_table:
                    for row in shape.table.rows:
                        row_texts = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                        if row_texts:
                            row_string = " | ".join(row_texts)
                            self._add_instruction_text(instruction_blocks, row_string, action_kind)
                    return

                # Text box / shape text
                if shape.has_text_frame and shape.text_frame.text.strip():
                    self._add_instruction_text(instruction_blocks, shape.text_frame.text, action_kind)
                    return

                # Image
                if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                    image_bytes = shape.image.blob
                    dims = ImageUtilities.try_get_dimensions(image_bytes)
                    if not dims:
                        return
                        
                    width, height = dims
                    image_idx += 1
                    
                    ocr_text = await self.ocr_service.extract_text(image_bytes)
                    
                    # Classify role
                    role = ImageContentClassifier.classify(
                        width, height, ocr_text,
                        settings.ingestion_min_vision_image_width,
                        settings.ingestion_min_vision_image_height
                    )
                    
                    if role == ImageRole.InlineIcon:
                        marker = ImageContentClassifier.build_inline_marker(ocr_text)
                        if marker:
                            self._add_instruction_text(instruction_blocks, marker, action_kind)
                        return
                    
                    # Screenshot placeholder in instruction text
                    self._add_instruction_text(instruction_blocks, ImageContentClassifier.build_screenshot_placeholder(), action_kind)
                    
                    # Vision description metadata
                    metadata = {
                        "source": file_name,
                        "slide": slide_index,
                        "type": "pptx_slide_image",
                        "content_kind": "image_ui_description",
                        "image_index": image_idx,
                        "width": width,
                        "height": height,
                        "image_role": role.value
                    }

                    caption = None
                    vision_attempted = False
                    
                    # Check vision budget limit
                    allow_vision = (
                        settings.ingestion_enable_vision_caption
                        and (settings.ingestion_max_vision_images_per_slide == 0 or slide_attempts < settings.ingestion_max_vision_images_per_slide)
                        and (settings.ingestion_max_vision_images_per_file == 0 or file_attempts < settings.ingestion_max_vision_images_per_file)
                        and width >= settings.ingestion_min_vision_image_width
                        and height >= settings.ingestion_min_vision_image_height
                    )

                    if allow_vision:
                        vision_attempted = True
                        slide_attempts += 1
                        file_attempts += 1
                        caption = await self.vision_service.generate_caption(image_bytes, metadata, ocr_text)

                    useful_caption = caption if VisionCaptionQuality.is_useful(caption, ocr_text) else None
                    desc_parts = [f"dimensions: {width}x{height}px"]
                    
                    if ocr_text and ocr_text.strip():
                        desc_parts.append(f"OCR text: {ocr_text.strip()}")
                    if useful_caption:
                        desc_parts.append(f"Vision caption: {useful_caption}")
                    elif vision_attempted and not ocr_text:
                        desc_parts.append("Vision caption was empty or filtered as unreliable")

                    if len(desc_parts) > 1 or vision_attempted:
                        desc_str = "; ".join(desc_parts)
                        image_chunks.append(IngestedDocument(
                            page_content=f"[MÔ TẢ GIAO DIỆN TỪ HÌNH ẢNH]\n[Hình ảnh trên slide: {desc_str}]",
                            metadata=metadata
                        ))

            for shape in slide.shapes:
                await process_shape(shape)

            # Emit merged slide instruction text doc
            valid_blocks = [b for b in instruction_blocks if b["text"].strip()]
            if valid_blocks:
                merged_text = "\n".join(b["text"] for b in valid_blocks)
                page_content = f"[SLIDE: {slide_title}]\n[VĂN BẢN HƯỚNG DẪN]\n{merged_text}" if slide_title else f"[VĂN BẢN HƯỚNG DẪN]\n{merged_text}"
                
                has_procedure = any(b["role"] == "procedure_steps" for b in valid_blocks)
                instruction_role = "procedure_steps" if has_procedure else "general"
                total_steps = sum(b["steps"] for b in valid_blocks)
                
                merged_action_kind = action_kind
                if not merged_action_kind:
                    # Fallback to action of first matching block
                    for b in valid_blocks:
                        if b["action"]:
                            merged_action_kind = b["action"]
                            break

                inst_meta = {
                    "source": file_name,
                    "slide": slide_index,
                    "type": "pptx_slide",
                    "content_kind": "instruction_text",
                    "instruction_role": instruction_role
                }
                
                if slide_title:
                    inst_meta["slide_title"] = slide_title
                if merged_action_kind:
                    inst_meta["action_kind"] = merged_action_kind
                if total_steps > 0:
                    inst_meta["step_count"] = total_steps

                yield IngestedDocument(page_content=page_content, metadata=inst_meta)

            # Emit image chunks
            for img_doc in image_chunks:
                if slide_title:
                    img_doc.metadata["slide_title"] = slide_title
                if action_kind:
                    img_doc.metadata["action_kind"] = action_kind
                yield img_doc

    def _detect_slide_title(self, slide) -> Optional[str]:
        # 1. Check title property
        try:
            if slide.shapes.title and slide.shapes.title.text.strip():
                return slide.shapes.title.text.strip()
        except Exception:
            pass

        # 2. Check placeholders
        for shape in slide.shapes:
            if shape.is_placeholder and shape.placeholder_format.type in (PP_PLACEHOLDER.TITLE, PP_PLACEHOLDER.CENTER_TITLE):
                if shape.has_text_frame and shape.text_frame.text.strip():
                    return shape.text_frame.text.strip()

        # 3. Check shapes with specific keywords
        for shape in slide.shapes:
            if shape.has_text_frame and shape.text_frame.text.strip():
                text = shape.text_frame.text.strip()
                if "tờ trình nghiệp vụ" in text.lower():
                    return text.split("\n")[0].strip()

        # 4. Fallback to first non-empty text shape
        for shape in slide.shapes:
            if shape.has_text_frame and shape.text_frame.text.strip():
                return shape.text_frame.text.strip().split("\n")[0].strip()

        return None

    def _add_instruction_text(self, blocks: List[Dict[str, Any]], text: str, action_kind: Optional[str]):
        cleaned = re.sub(r'\s+', ' ', text).strip()
        if not cleaned:
            return

        extracted = ProcedureBlockExtractor.extract(cleaned, action_kind)
        for block in extracted:
            blocks.append({
                "text": block.text,
                "role": block.instruction_role,
                "action": block.action_kind,
                "steps": block.step_count
            })

    def _parse_fallback(self, file_path: str, file_name: str) -> List[IngestedDocument]:
        # C# lines 230-286: Parse text from Zip XML structure directly
        docs = []
        try:
            with zipfile.ZipFile(file_path, "r") as archive:
                slide_entries = [
                    name for name in archive.namelist()
                    if name.lower().startswith("ppt/slides/slide") 
                    and name.lower().endswith(".xml") 
                    and "/_rels/" not in name.lower()
                ]
                
                # Sort slide entries numerically
                def get_slide_num(name):
                    m = re.search(r'slide(\d+)\.xml$', name, re.IGNORECASE)
                    return int(m.group(1)) if m else 9999
                
                slide_entries.sort(key=get_slide_num)
                
                for slide_index, entry_name in enumerate(slide_entries, start=1):
                    with archive.open(entry_name) as file:
                        xml_content = file.read().decode("utf-8")
                        # Extract all <a:t> texts
                        texts = re.findall(r'<a:t[^>]*>(.*?)</a:t>', xml_content)
                        texts = [t.strip() for t in texts if t.strip()]
                        
                        if texts:
                            slide_text = "\n".join(texts)
                            docs.append(IngestedDocument(
                                page_content=f"[VĂN BẢN HƯỚNG DẪN]\n{slide_text}",
                                metadata={
                                    "source": file_name,
                                    "slide": slide_index,
                                    "type": "pptx_slide_text_fallback",
                                    "content_kind": "instruction_text"
                                }
                            ))
        except Exception as ex:
            logger.error(f"ZIP fallback failed for {file_name}: {ex}")
        return docs
