import io
import os
import logging
from typing import Optional
from PIL import Image
import pytesseract
import anyio
from app.config import settings
from app.ingestion.image_utils import ImageUtilities
from app.ingestion.text_cleaner import TextArtifactCleaner

logger = logging.getLogger(__name__)

class TesseractOcrService:
    def __init__(self):
        self.enabled = settings.ingestion_enable_ocr
        if settings.ingestion_tessdata_path:
            os.environ["TESSDATA_PREFIX"] = settings.ingestion_tessdata_path

    async def extract_text(self, image_bytes: bytes) -> Optional[str]:
        if not self.enabled or not image_bytes:
            return None

        dims = ImageUtilities.try_get_dimensions(image_bytes)
        if not dims or ImageUtilities.should_skip_ocr(dims[0], dims[1]):
            return None

        tessdata_path = settings.ingestion_tessdata_path
        lang = "eng+vie"
        if tessdata_path and os.path.exists(tessdata_path):
            has_eng = os.path.exists(os.path.join(tessdata_path, "eng.traineddata"))
            has_vie = os.path.exists(os.path.join(tessdata_path, "vie.traineddata"))
            if has_eng and has_vie:
                lang = "eng+vie"
            elif has_vie:
                lang = "vie"
            elif has_eng:
                lang = "eng"

        try:
            # Create OCR image variants (binarized, padded, scaled)
            variants = ImageUtilities.prepare_ocr_variants(image_bytes)
            for variant in variants:
                # Open PIL image
                img = Image.open(io.BytesIO(variant))
                
                # Execute OCR inside an anyio threadpool to prevent blocking the async loop
                def run_ocr():
                    return pytesseract.image_to_string(
                        img, 
                        lang=lang, 
                        config="--psm 3 -c preserve_interword_spaces=1"
                    )
                
                text = await anyio.to_thread.run_sync(run_ocr)
                
                cleaned = TextArtifactCleaner.clean(text)
                if cleaned and cleaned.strip():
                    return cleaned
            return None
        except Exception as ex:
            logger.warning(f"Pytesseract OCR extraction failed: {ex}")
            return None
