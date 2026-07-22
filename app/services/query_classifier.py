import re
import unicodedata
from enum import Enum

class QueryIntent(str, Enum):
    TaskInstruction = "TaskInstruction"
    UiLocation = "UiLocation"
    General = "General"

class QueryClassifier:
    TaskKeywords = [
        "cach", "cac buoc", "buoc", "huong dan", "quy trinh", "trinh tu", "thao tac", "lam sao", "lam the nao", "nhu the nao",
        "thuc hien", "tao", "them", "sua", "xoa", "duyet", "tim kiem", "lam gi", "lam nhung gi", "can lam gi", "phai lam gi"
    ]

    UiKeywords = [
        "o dau", "nam o", "nam dau", "cho nao", "cot nao", "o nao", "vi tri", "co nhung gi", "gom nhung gi", "hien thi gi", "layout",
        "nut", "truong", "man hinh", "giao dien", "tab", "menu", "sidebar", "toolbar", "ben trai", "ben phai", "phia tren", "phia duoi", "truong nao", "panel"
    ]

    Exclusions = [
        ("tao", "dao tao"),
        ("buoc", "bat buoc")
    ]

    @staticmethod
    def classify(message: str) -> QueryIntent:
        normalized = QueryClassifier.normalize_vietnamese(message)
        
        has_task = QueryClassifier.contains_any(normalized, QueryClassifier.TaskKeywords)
        has_ui = QueryClassifier.contains_any(normalized, QueryClassifier.UiKeywords)

        if has_task and not has_ui:
            return QueryIntent.TaskInstruction
        if has_ui and not has_task:
            return QueryIntent.UiLocation
        return QueryIntent.General

    @staticmethod
    def contains_any(text: str, keywords: list) -> bool:
        for keyword in keywords:
            if QueryClassifier.match_keyword_with_exclusions(text, keyword):
                return True
        return False

    @staticmethod
    def match_keyword_with_exclusions(text: str, keyword: str) -> bool:
        # Boundary-aware check using regex
        # Python \w represents [a-zA-Z0-9_] in Unicode. For exact Vietnamese matches,
        # checking word boundaries with (?<!\w) and (?!\w) is perfect.
        keyword_pattern = rf"(?<!\w){re.escape(keyword)}(?!\w)"
        matches = list(re.finditer(keyword_pattern, text, re.IGNORECASE))
        if not matches:
            return False

        # Exclusions configured for this keyword
        exclusions = [e[1] for e in QueryClassifier.Exclusions if e[0] == keyword]
        if not exclusions:
            return True

        excluded_spans = []
        for phrase in exclusions:
            phrase_pattern = rf"(?<!\w){re.escape(phrase)}(?!\w)"
            phrase_matches = re.finditer(phrase_pattern, text, re.IGNORECASE)
            for pm in phrase_matches:
                excluded_spans.append((pm.start(), pm.end()))

        # At least one keyword match must not fall within any excluded phrase matches
        for m in matches:
            m_start, m_end = m.start(), m.end()
            is_excluded = False
            for span_start, span_end in excluded_spans:
                if m_start >= span_start and m_end <= span_end:
                    is_excluded = True
                    break
            
            if not is_excluded:
                return True

        return False

    @staticmethod
    def normalize_vietnamese(text: str) -> str:
        # Normalize Unicode FormD, convert to lowercase
        normalized = text.strip().lower()
        normalized = unicodedata.normalize('NFKD', normalized)
        
        builder = []
        for ch in normalized:
            if ch == '\u0111' or ch == 'đ':
                builder.append('d')
            elif ch == '\u0110' or ch == 'Đ':
                builder.append('d')
            elif unicodedata.category(ch) != 'Mn':
                builder.append(ch)

        composed = unicodedata.normalize('NFC', "".join(builder))
        # Collapse whitespaces and return
        return " ".join(composed.split())
