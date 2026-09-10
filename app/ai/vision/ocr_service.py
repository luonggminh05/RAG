import io
import os
import hashlib
import logging
from typing import Optional
from PIL import Image
import pytesseract
import anyio
from cachetools import TTLCache
from app.core.config import settings
from app.ai.vision.image_utils import ImageUtilities
from app.ai.rag.text.text_cleaner import TextArtifactCleaner

logger = logging.getLogger(__name__)

class TesseractOcrService:
    def __init__(self):
        self.enabled = getattr(settings, "ingestion_enable_ocr", True)
        tessdata_path = getattr(settings, "ingestion_tessdata_path", "tessdata")
        if tessdata_path:
            os.environ["TESSDATA_PREFIX"] = tessdata_path
        self._ocr_cache = TTLCache(maxsize=1024, ttl=86400)

    async def extract_text(self, image_bytes: bytes) -> Optional[str]:
        if not self.enabled or not image_bytes:
            return None

        image_hash = hashlib.sha256(image_bytes).hexdigest()[:16]
        if image_hash in self._ocr_cache:
            logger.debug(f"[OCR] Cache hit for image_hash={image_hash}")
            return self._ocr_cache[image_hash]

        dims = ImageUtilities.try_get_dimensions(image_bytes)
        if not dims or ImageUtilities.should_skip_ocr(dims[0], dims[1]):
            return None

        tessdata_path = getattr(settings, "ingestion_tessdata_path", "tessdata")
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
            variants = ImageUtilities.prepare_ocr_variants(image_bytes)
            for variant in variants:
                img = Image.open(io.BytesIO(variant))
                
                def run_ocr():
                    return pytesseract.image_to_string(
                        img, 
                        lang=lang, 
                        config="--psm 3 -c preserve_interword_spaces=1"
                    )
                
                text = await anyio.to_thread.run_sync(run_ocr)
                cleaned = TextArtifactCleaner.clean(text)
                if cleaned and cleaned.strip():
                    self._ocr_cache[image_hash] = cleaned
                    return cleaned
            return None
        except Exception as ex:
            logger.warning(f"[OCR] Pytesseract extraction failed or skipped: {ex}")
            return None
