import re
import unicodedata
from typing import Optional, List

class ActionKindClassifier:
    TimKiem = "tim_kiem"
    ThemMoi = "them_moi"
    LuuNhap = "luu_nhap"
    GuiPheDuyet = "gui_phe_duyet"
    Duyet = "duyet"
    TuChoi = "tu_choi"
    UyQuyen = "uy_quyen"
    BanGiao = "ban_giao"
    ChiaSe = "chia_se"
    In = "in"
    ThemGhiChu = "them_ghi_chu"
    DinhKem = "dinh_kem"

    # Tuple of (Kind, Phrase)
    Patterns = [
        (GuiPheDuyet, "gui phe duyet"),
        (ThemGhiChu, "them ghi chu"),
        (TimKiem, "tim kiem"),
        (ThemMoi, "them moi"),
        (LuuNhap, "luu nhap"),
        (TuChoi, "tu choi"),
        (UyQuyen, "uy quyen"),
        (BanGiao, "ban giao"),
        (ChiaSe, "chia se"),
        (Duyet, "phe duyet"),
        (ThemMoi, "tao moi"),
        (ThemMoi, "them"),
        (Duyet, "duyet"),
        (In, "in"),
        (DinhKem, "dinh kem hinh anh"),
        (DinhKem, "dinh kem anh"),
        (DinhKem, "dinh kem file"),
        (DinhKem, "dinh kem"),
        (TimKiem, "xem chi tiet")
    ]

    # Sort by phrase length descending
    OrderedPatterns = sorted(Patterns, key=lambda x: len(x[1]), reverse=True)

    AllActionKinds = [
        TimKiem, ThemMoi, LuuNhap, GuiPheDuyet, Duyet, TuChoi,
        UyQuyen, BanGiao, ChiaSe, In, ThemGhiChu, DinhKem
    ]

    @staticmethod
    def normalize_text(text: Optional[str]) -> str:
        if not text or not text.strip():
            return ""

        # Normalize to FormD, lowercase
        normalized = unicodedata.normalize('NFKD', text.strip().lower())
        builder = []
        for ch in normalized:
            if ch == '\u0111' or ch == 'đ':
                builder.append('d')
            elif ch == '\u0110' or ch == 'Đ':
                builder.append('d')
            elif unicodedata.category(ch) != 'Mn':
                builder.append(ch)

        composed = unicodedata.normalize('NFC', "".join(builder))
        # Collapse multiple spaces into one
        return re.sub(r'\s+', ' ', composed).strip()

    @staticmethod
    def determine_action_kind(text: Optional[str]) -> Optional[str]:
        normalized = ActionKindClassifier.normalize_text(text)
        if not normalized:
            return None

        for kind, phrase in ActionKindClassifier.OrderedPatterns:
            if ActionKindClassifier._contains_phrase(normalized, phrase):
                return kind
        return None

    @staticmethod
    def has_action_intent(text: Optional[str]) -> bool:
        return ActionKindClassifier.determine_action_kind(text) is not None

    @staticmethod
    def normalize_action_kind(raw: Optional[str]) -> Optional[str]:
        if not raw or not raw.strip():
            return None
        normalized = raw.strip().lower()
        if normalized == "phe_duyet":
            return ActionKindClassifier.Duyet
        return normalized

    @staticmethod
    def get_action_keyword(action_kind: Optional[str]) -> Optional[str]:
        normalized = ActionKindClassifier.normalize_action_kind(action_kind)
        if normalized == ActionKindClassifier.TimKiem:
            return "tim kiem"
        elif normalized == ActionKindClassifier.ThemMoi:
            return "them moi"
        elif normalized == ActionKindClassifier.LuuNhap:
            return "luu nhap"
        elif normalized == ActionKindClassifier.GuiPheDuyet:
            return "gui phe duyet"
        elif normalized == ActionKindClassifier.Duyet:
            return "duyet"
        elif normalized == ActionKindClassifier.TuChoi:
            return "tu choi"
        elif normalized == ActionKindClassifier.UyQuyen:
            return "uy quyen"
        elif normalized == ActionKindClassifier.BanGiao:
            return "ban giao"
        elif normalized == ActionKindClassifier.ChiaSe:
            return "chia se"
        elif normalized == ActionKindClassifier.In:
            return "in"
        elif normalized == ActionKindClassifier.ThemGhiChu:
            return "them ghi chu"
        elif normalized == ActionKindClassifier.DinhKem:
            return "dinh kem"
        return None

    @staticmethod
    def _contains_phrase(normalized_text: str, normalized_phrase: str) -> bool:
        if normalized_phrase == ActionKindClassifier.In:
            return bool(re.search(r'\bin\b', normalized_text))
        
        # Regex escape the phrase and look for word boundaries/spaces
        escaped_phrase = re.escape(normalized_phrase)
        pattern = rf"(^|\s){escaped_phrase}(\s|$)"
        return bool(re.search(pattern, normalized_text))
