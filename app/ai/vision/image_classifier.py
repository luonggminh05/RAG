import re
import unicodedata
from enum import Enum
from typing import Optional

class ImageRole(Enum):
    InlineIcon = "inlineicon"
    UiScreenshot = "uiscreenshot"
    UnknownImage = "unknownimage"

class ImageContentClassifier:
    InlineOcrMaxLength = 50

    @staticmethod
    def classify(
        width: int, 
        height: int, 
        ocr_text: Optional[str], 
        min_vision_width: int, 
        min_vision_height: int
    ) -> ImageRole:
        is_small_image = width < min_vision_width or height < min_vision_height
        has_ocr = bool(ocr_text and ocr_text.strip())
        is_short_ocr = has_ocr and len(ocr_text) <= ImageContentClassifier.InlineOcrMaxLength

        if is_small_image and is_short_ocr:
            return ImageRole.InlineIcon
        if is_small_image and not has_ocr:
            return ImageRole.InlineIcon
        if not is_small_image:
            return ImageRole.UiScreenshot
        return ImageRole.UnknownImage

    @staticmethod
    def build_inline_marker(ocr_text: Optional[str]) -> Optional[str]:
        if ocr_text and ocr_text.strip():
            return f"[Nút/Ảnh: {ocr_text.strip()}]"
        return None

    @staticmethod
    def build_screenshot_placeholder() -> str:
        return "[Ảnh giao diện]"


class VisionCaptionQuality:
    @staticmethod
    def normalize_text(text: str) -> str:
        normalized = unicodedata.normalize("NFKD", text.strip().lower())
        stripped = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
        cleaned = stripped.replace('\u0111', 'd').replace('\u0110', 'd')
        return re.sub(r'\s+', ' ', cleaned).strip()

    @staticmethod
    def is_useful(caption: Optional[str], ocr_text: Optional[str]) -> bool:
        if not caption or not caption.strip():
            return False
        normalized = VisionCaptionQuality.normalize_text(caption)
        if len(normalized) < 40:
            return False
        if caption.count('?') >= 5:
            return False
        return True
