import re
import unicodedata

class VietnameseNormalizer:
    """
    Normalizer for Vietnamese text before ingestion and semantic chunking.
    Preserves Vietnamese accents for vector embedding quality.
    """
    _HORIZ_WHITESPACE = re.compile(r'[ \t\f\v]+')
    _MULTIPLE_NEWLINES = re.compile(r'\n{3,}')

    _BUSINESS_ACRONYMS = [
        (re.compile(r'\bSTK\b', re.IGNORECASE), "Số tài khoản"),
        (re.compile(r'\bTK\b', re.IGNORECASE), "Tài khoản"),
        (re.compile(r'\bKH\b', re.IGNORECASE), "Khách hàng"),
        (re.compile(r'\bGDV\b', re.IGNORECASE), "Giao dịch viên"),
        (re.compile(r'\bPGD\b', re.IGNORECASE), "Phòng giao dịch"),
        (re.compile(r'\bCN\b', re.IGNORECASE), "Chi nhánh"),
        (re.compile(r'\bPYC\b', re.IGNORECASE), "Phiếu yêu cầu"),
        (re.compile(r'\bVPP\b', re.IGNORECASE), "Văn phòng phẩm"),
        (re.compile(r'\bHDSD\b', re.IGNORECASE), "Hướng dẫn sử dụng"),
        (re.compile(r'\bTSCĐ\b', re.IGNORECASE), "Tài sản cố định"),
        (re.compile(r'\bCCLD\b', re.IGNORECASE), "Công cụ lao động"),
    ]

    _ZERO_WIDTH_PATTERN = re.compile(r'[\u200b\u200c\u200d\ufeff\u200e\u200f\u202a-\u202e\x00-\x08\x0b\x0c\x0e-\x1f]')

    _TONE_REPLACEMENTS = [
        ("óa", "oá"), ("òa", "oà"), ("ỏa", "oả"), ("õa", "oã"), ("ọa", "oạ"),
        ("óe", "oé"), ("òe", "oè"), ("ỏe", "oẻ"), ("õe", "oẽ"), ("ọe", "oẹ"),
        ("úy", "uý"), ("ùy", "uỳ"), ("ủy", "uỷ"), ("ũy", "uỹ"), ("ụy", "uỵ"),
        ("Óa", "Oá"), ("Òa", "Oà"), ("Ỏa", "Oả"), ("Õa", "Oã"), ("Ọa", "Oạ"),
        ("Óe", "Oé"), ("Òe", "Oè"), ("Ỏe", "Oẻ"), ("Õe", "Oẽ"), ("Ọe", "Oẹ"),
        ("Úy", "Uý"), ("Ùy", "Uỳ"), ("Ủy", "Uỷ"), ("Ũy", "Uỹ"), ("Ụy", "Uỵ"),
        ("ÓA", "OÁ"), ("ÒA", "OÀ"), ("ỎA", "OẢ"), ("ÕA", "OÃ"), ("ỌA", "OẠ"),
        ("ÓE", "OÉ"), ("ÒE", "OÈ"), ("ỎE", "OẺ"), ("ÕE", "OẼ"), ("ỌE", "OẸ"),
        ("ÚY", "UÝ"), ("ÙY", "UỲ"), ("ỦY", "UỶ"), ("ŨY", "UỸ"), ("ỤY", "UÝ")
    ]

    @classmethod
    def normalize(cls, text: str, expand_acronyms: bool = True) -> str:
        if not text:
            return ""

        # 1. Unicode NFC
        text = unicodedata.normalize('NFC', text)

        # 2. Xóa khoảng trắng thừa
        lines = [cls._HORIZ_WHITESPACE.sub(' ', line).strip() for line in text.split('\n')]
        text = '\n'.join(lines)

        # 3. Chuẩn hóa newline
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        text = cls._MULTIPLE_NEWLINES.sub('\n\n', text)

        # 4. Viết tắt
        if expand_acronyms:
            for pattern, replacement in cls._BUSINESS_ACRONYMS:
                text = pattern.sub(replacement, text)

        # 5. Zero-width & Punctuation
        text = cls._ZERO_WIDTH_PATTERN.sub('', text)
        text = re.sub(r'([a-zA-Zà-ỹÀ-Ỹ])\s+([,.;:!?])', r'\1\2', text)
        text = re.sub(r'([,;:!?])([a-zA-Zà-ỹÀ-Ỹ])', r'\1 \2', text)
        text = re.sub(r'\.([A-ZÀ-Ỹ])', r'. \1', text)

        # 6. Dấu thanh
        for old_tone, new_tone in cls._TONE_REPLACEMENTS:
            text = text.replace(old_tone, new_tone)

        return text.strip()
