import re
import unicodedata
from typing import Dict, Optional

class TextArtifactCleaner:
    @staticmethod
    def clean(text: str, line_occurrences: Optional[Dict[str, int]] = None) -> str:
        if not text or not text.strip():
            return ""

        lines = text.splitlines()
        cleaned_lines = []
        local_occurrences = line_occurrences if line_occurrences is not None else {}

        for line in lines:
            trimmed = line.strip()
            if not trimmed:
                continue

            # Remove obvious math/latex syntax artifacts
            if "\\begin" in trimmed or "\\end" in trimmed or "\\[" in trimmed or "\\]" in trimmed:
                continue

            # Remove lines that contain no letters or digits (pure table lines / dividers)
            # character classification: char.isalnum()
            if not any(c.isalnum() for c in trimmed):
                continue

            # Deduplication by normalized line to remove repeated slide headers, footers, etc.
            normalized = TextArtifactCleaner.normalize_text(trimmed)
            count = local_occurrences.get(normalized, 0)
            if count >= 2:
                continue

            local_occurrences[normalized] = count + 1
            cleaned_lines.append(trimmed)

        return "\n".join(cleaned_lines)

    @staticmethod
    def normalize_text(text: str) -> str:
        # Lowercase and decompose unicode diacritics
        normalized = unicodedata.normalize('NFKD', text.strip().lower())
        
        builder = []
        for character in normalized:
            # Check for non-spacing marks (diacritics in decomposed form)
            # Also replace Vietnamese 'đ' (unicode \u0111) with 'd'
            if character == '\u0111' or character == 'đ':
                builder.append('d')
            elif character == '\u0110' or character == 'Đ':
                builder.append('d')
            elif unicodedata.category(character) != 'Mn':
                builder.append(character)

        # Re-compose unicode string and collapse extra spaces
        composed = unicodedata.normalize('NFC', "".join(builder))
        return " ".join(composed.split())

    @staticmethod
    def collapse_icon_gaps(text: Optional[str]) -> str:
        if not text or not text.strip():
            return ""

        # Normalize line breaks
        normalized = text.replace("\r\n", "\n").replace('\r', '\n')
        
        # Matches tabs with spaces, or 8+ spaces
        pattern = r'[ \t]*\t[ \t]*| {8,}'
        
        def replace_match(match):
            index = match.start()
            text_before = normalized[:index].rstrip()
            
            last_25 = text_before[-25:] if len(text_before) >= 25 else text_before
            has_nut_nearby = "nút" in last_25.lower() or "nut" in last_25.lower()
            
            return " " if has_nut_nearby else " nút "

        # Regex replacement using callback
        normalized = re.sub(pattern, replace_match, normalized)

        # Collapse other spacing issues
        normalized = re.sub(r'[ \f\v]+', ' ', normalized)
        normalized = re.sub(r' *\n *', '\n', normalized)
        return normalized.strip()
