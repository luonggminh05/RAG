import re
import unicodedata
from enum import Enum
from typing import Optional, List

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

        # Small image with readable short text is treated as an inline icon/button
        if is_small_image and is_short_ocr:
            return ImageRole.InlineIcon
            
        # Small image with no text may be an icon-only button; keep it inline
        if is_small_image and not has_ocr:
            return ImageRole.InlineIcon
            
        # Large images are treated as screenshots even when OCR is short or empty
        if not is_small_image:
            return ImageRole.UiScreenshot
            
        # Small image with long OCR is unusual; fall back conservatively
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
    GenericPhrases = [
        "this image shows",
        "this image contains",
        "this is a web page",
        "software interface",
        "web browser",
        "rag search system",
        "below is a description",
        "duoi day la mo ta",
        "hinh anh nay cho thay",
        "giao dien phan mem",
        "trinh duyet web",
        "cong cu ocr"
    ]

    PlaceholderEchoes = [
        "<visible title",
        "<visible text",
        "<verbatim important",
        "<table names",
        "<button names",
        "<only if useful",
        "<ghi ",
        "<chep ",
        "<liet ke ",
        "<chi ghi "
    ]

    @staticmethod
    def normalize_text(text: str) -> str:
        normalized = unicodedata.normalize("NFKD", text.strip().lower())
        # Strip diacritics
        stripped = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
        # Replace 'đ' with 'd'
        cleaned = stripped.replace('\u0111', 'd').replace('\u0110', 'd')
        # Collapse whitespace
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

        # Contains CJK
        if any('\u4E00' <= ch <= '\u9FFF' for ch in caption):
            return False

        if any(echo in normalized for echo in VisionCaptionQuality.PlaceholderEchoes):
            return False

        if (
            VisionCaptionQuality._has_repeated_lines(caption) 
            or VisionCaptionQuality._has_degenerate_repetition(caption) 
            or VisionCaptionQuality._has_numeric_runaway(caption)
        ):
            return False

        # Evidence keywords
        evidences = [
            "image_type", "system_or_app_name", "screen_or_document_title", "visible_text", "ui_panels", "search_conditions", "data_tables", "email_info", "buttons_or_actions", "counts", "question_answer_hints", "searchable_summary",
            "dieu kien", "tim kiem", "to trinh", "so to", "trang thai", "ngay", "tu ngay", "den ngay",
            "nut", "bang", "cot", "dong", "o nhap", "checkbox", "combobox", "button", "field", "table", "panel", "textbox", "dropdown", "date-picker", "email", "from", "subject", "attachment",
            "man hinh", "giao dien", "he thong", "chuc nang", "hien thi", "mo ta", "bieu mau", "danh sach", "nhap lieu", "thong tin"
        ]
        
        has_structured_evidence = any(ev in normalized for ev in evidences)

        if not has_structured_evidence and any(p in normalized for p in VisionCaptionQuality.GenericPhrases):
            return False

        if not has_structured_evidence:
            return False

        # Count alphabetical letters
        letter_count = sum(c.isalpha() for c in caption)
        return letter_count >= 20

    @staticmethod
    def _has_degenerate_repetition(text: str) -> bool:
        normalized = VisionCaptionQuality.normalize_text(text)
        tokens = [t for t in normalized.split(' ') if t]
        if len(tokens) < 20:
            return False
            
        freqs = {}
        for t in tokens:
            freqs[t] = freqs.get(t, 0) + 1
            
        most_common_token_count = max(freqs.values()) if freqs else 0
        return most_common_token_count >= 12 or most_common_token_count >= len(tokens) * 0.45

    @staticmethod
    def _has_numeric_runaway(text: str) -> bool:
        compact = re.sub(r'\s+', '', text)
        if len(compact) < 120:
            return False
            
        digit_count = sum(c.isdigit() for c in compact)
        letter_count = sum(c.isalpha() for c in compact)
        
        if digit_count > letter_count * 3 and re.search(r'(?:\d[\d.,]*){80,}', compact):
            return True
            
        return bool(re.search(r'(?:0{8,}|0001|0002|\.000){8,}', compact))

    @staticmethod
    def _has_repeated_lines(text: str) -> bool:
        lines = [VisionCaptionQuality.normalize_text(l) for l in text.splitlines() if l.strip()]
        lines = [l for l in lines if len(l) > 12]
        
        if len(lines) < 4:
            return False
            
        freqs = {}
        for l in lines:
            freqs[l] = freqs.get(l, 0) + 1
            
        return any(count >= 3 for count in freqs.values())
