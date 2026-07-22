import re
import unicodedata

class VietnameseNormalizer:
    """
    Normalizer for Vietnamese text before ingestion and semantic chunking.
    Preserves Vietnamese accents for vector embedding quality.
    """

    # Zero-width and control character pattern
    _ZERO_WIDTH_PATTERN = re.compile(r'[\u200b\u200c\u200d\ufeff\u200e\u200f\u202a-\u202e\x00-\x08\x0b\x0c\x0e-\x1f]')
    
    # Horizontal whitespace pattern (spaces, tabs)
    _HORIZ_WHITESPACE = re.compile(r'[ \t\f\v]+')
    
    # Excessive blank lines pattern (3 or more newlines -> 2 newlines)
    _MULTIPLE_NEWLINES = re.compile(r'\n{3,}')

    # Optional business acronym replacements
    _BUSINESS_ACRONYMS = [
        (re.compile(r'\bSTK\b'), "Số tài khoản"),
        (re.compile(r'\bTK\b'), "Tài khoản"),
        (re.compile(r'\bKH\b'), "Khách hàng"),
        (re.compile(r'\bGDV\b'), "Giao dịch viên"),
        (re.compile(r'\bPGD\b'), "Phòng giao dịch"),
        (re.compile(r'\bCN\b'), "Chi nhánh"),
    ]

    @classmethod
    def normalize(cls, text: str, expand_acronyms: bool = False) -> str:
        if not text:
            return ""

        # 1. Unicode NFC Normalization
        text = unicodedata.normalize('NFC', text)

        # 2. Remove zero-width and control characters
        text = cls._ZERO_WIDTH_PATTERN.sub('', text)

        # 3. Standardize newlines (\r\n -> \n, \r -> \n)
        text = text.replace('\r\n', '\n').replace('\r', '\n')

        # 4. Collapse spaces on each line
        lines = [cls._HORIZ_WHITESPACE.sub(' ', line).strip() for line in text.split('\n')]
        text = '\n'.join(lines)

        # 5. Collapse 3+ newlines to max 2
        text = cls._MULTIPLE_NEWLINES.sub('\n\n', text)

        # 6. Optional business acronym expansion
        if expand_acronyms:
            for pattern, replacement in cls._BUSINESS_ACRONYMS:
                text = pattern.sub(replacement, text)

        return text.strip()
