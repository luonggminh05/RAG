import re
import unicodedata

class VietnameseNormalizer:
    """
    Normalizer for Vietnamese text before ingestion and semantic chunking.
    Preserves Vietnamese accents for vector embedding quality.
    Follows a fixed pipeline order:
    Unicode NFC -> Xóa khoảng trắng thừa -> Chuẩn hóa newline -> Viết tắt (STK/TK...) -> Chuẩn hóa tiếng Việt (dấu câu, zero-width; giữ dấu thanh)
    """

    # Horizontal whitespace pattern (spaces, tabs)
    _HORIZ_WHITESPACE = re.compile(r'[ \t\f\v]+')
    
    # Excessive blank lines pattern (3 or more newlines -> 2 newlines)
    _MULTIPLE_NEWLINES = re.compile(r'\n{3,}')

    # Business acronym replacements (expand mapping)
    _BUSINESS_ACRONYMS = [
        (re.compile(r'\bSTK\b'), "Số tài khoản"),
        (re.compile(r'\bTK\b'), "Tài khoản"),
        (re.compile(r'\bKH\b'), "Khách hàng"),
        (re.compile(r'\bGDV\b'), "Giao dịch viên"),
        (re.compile(r'\bPGD\b'), "Phòng giao dịch"),
        (re.compile(r'\bCN\b'), "Chi nhánh"),
    ]

    # Zero-width and control character pattern
    _ZERO_WIDTH_PATTERN = re.compile(r'[\u200b\u200c\u200d\ufeff\u200e\u200f\u202a-\u202e\x00-\x08\x0b\x0c\x0e-\x1f]')

    # Accent / Tone mark replacements (normalize old-style to modern new-style)
    _TONE_REPLACEMENTS = [
        ("óa", "oá"), ("òa", "oà"), ("ỏa", "oả"), ("õa", "oã"), ("ọa", "oạ"),
        ("óe", "oé"), ("òe", "oè"), ("ỏe", "oẻ"), ("õe", "oẽ"), ("ọe", "oẹ"),
        ("úy", "uý"), ("ùy", "uỳ"), ("ủy", "uỷ"), ("ũy", "uỹ"), ("ụy", "uỵ"),
        # Capitalized
        ("Óa", "Oá"), ("Òa", "Oà"), ("Ỏa", "Oả"), ("Õa", "Oã"), ("Ọa", "Oạ"),
        ("Óe", "Oé"), ("Òe", "Oè"), ("Ỏe", "Oẻ"), ("Õe", "Oẽ"), ("Ọe", "Oẹ"),
        ("Úy", "Uý"), ("Ùy", "Uỳ"), ("Ủy", "Uỷ"), ("Ũy", "Uỹ"), ("Ụy", "Uỵ"),
        # Uppercase
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

        # 2. Xóa khoảng trắng thừa (trim dòng và gộp các space liên tiếp)
        lines = [cls._HORIZ_WHITESPACE.sub(' ', line).strip() for line in text.split('\n')]
        text = '\n'.join(lines)

        # 3. Chuẩn hóa newline (\r\n -> \n, \r -> \n, gộp 3+ dòng trống thành tối đa 2 dòng trống)
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        text = cls._MULTIPLE_NEWLINES.sub('\n\n', text)

        # 4. Viết tắt (STK/TK…, map mở rộng)
        if expand_acronyms:
            for pattern, replacement in cls._BUSINESS_ACRONYMS:
                text = pattern.sub(replacement, text)

        # 5. Chuẩn hóa tiếng Việt (dấu câu, zero-width; giữ dấu thanh)
        # a) Loại bỏ ký tự zero-width và ký tự điều khiển
        text = cls._ZERO_WIDTH_PATTERN.sub('', text)

        # b) Chuẩn hóa khoảng trắng quanh dấu câu (tránh làm hỏng tên file .py, .docx hoặc số thập phân)
        text = re.sub(r'([a-zA-Zà-ỹÀ-Ỹ])\s+([,.;:!?])', r'\1\2', text)
        text = re.sub(r'([,;:!?])([a-zA-Zà-ỹÀ-Ỹ])', r'\1 \2', text)
        text = re.sub(r'\.([A-ZÀ-Ỹ])', r'. \1', text)

        # c) Chuẩn hóa đặt dấu thanh (đồng nhất hóa sang kiểu mới nhưng giữ nguyên dấu thanh gốc)
        for old_tone, new_tone in cls._TONE_REPLACEMENTS:
            text = text.replace(old_tone, new_tone)

        return text.strip()
