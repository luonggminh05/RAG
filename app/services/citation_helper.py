from typing import List, Dict, Any, Tuple, Optional

class FooterPosition:
    def __init__(self, label: str, unit: str):
        self.label = label
        self.unit = unit

class FooterGroup:
    def __init__(self, source: str):
        self.source = source
        self.positions: List[FooterPosition] = []

class CitationHelper:
    MaxFooterFiles = 3
    MaxFooterPositionsPerFile = 3
    MaxDocxTitleLength = 50

    @staticmethod
    def get_string(metadata: Dict[str, Any], property_name: str) -> Optional[str]:
        val = metadata.get(property_name)
        if val is None:
            return None
        return str(val)

    @staticmethod
    def has_property(metadata: Dict[str, Any], property_name: str) -> bool:
        return property_name in metadata

    @staticmethod
    def get_citation_identity(metadata: Dict[str, Any]) -> str:
        source = CitationHelper.get_string(metadata, "source") or ""
        doc_type = CitationHelper.get_string(metadata, "type") or ""

        # PDF check
        if doc_type.lower().startswith("pdf") or CitationHelper.has_property(metadata, "page"):
            if not doc_type.lower().startswith("pptx") and not CitationHelper.has_property(metadata, "slide"):
                page = CitationHelper.get_string(metadata, "page") or ""
                return f"{source}|page|{page}"

        # PPTX check
        if doc_type.lower().startswith("pptx") or CitationHelper.has_property(metadata, "slide"):
            slide = CitationHelper.get_string(metadata, "slide") or ""
            return f"{source}|slide|{slide}"

        # DOCX check
        if doc_type.lower().startswith("docx"):
            page_title = CitationHelper.get_string(metadata, "page_title")
            if page_title and page_title.strip():
                return f"{source}|page_title|{page_title}"
            
            paragraph_index = CitationHelper.get_string(metadata, "paragraph_index")
            if paragraph_index and paragraph_index.strip():
                return f"{source}|paragraph_index|{paragraph_index}"

        # Tabular check
        if CitationHelper.has_property(metadata, "row"):
            row = CitationHelper.get_string(metadata, "row") or ""
            return f"{source}|row|{row}"

        return source

    @staticmethod
    def build_citation_label(metadata: Dict[str, Any]) -> str:
        source = CitationHelper.get_string(metadata, "source") or "unknown"
        doc_type = CitationHelper.get_string(metadata, "type") or ""

        # PDF
        if doc_type.lower().startswith("pdf") or CitationHelper.has_property(metadata, "page"):
            if not doc_type.lower().startswith("pptx") and not CitationHelper.has_property(metadata, "slide"):
                page = CitationHelper.get_string(metadata, "page")
                return f"{source}, trang {page}" if page else source

        # PPTX
        if doc_type.lower().startswith("pptx") or CitationHelper.has_property(metadata, "slide"):
            slide = CitationHelper.get_string(metadata, "slide")
            return f"{source}, slide {slide}" if slide else source

        # DOCX
        if doc_type.lower().startswith("docx"):
            page_title = CitationHelper.get_string(metadata, "page_title")
            if page_title and page_title.strip():
                truncated = (
                    page_title[:CitationHelper.MaxDocxTitleLength] + "..."
                    if len(page_title) > CitationHelper.MaxDocxTitleLength
                    else page_title
                )
                return f"{source}, mục \"{truncated}\""
            
            paragraph_index = CitationHelper.get_string(metadata, "paragraph_index")
            if paragraph_index and paragraph_index.strip():
                return f"{source}, đoạn {paragraph_index}"

        # XLSX/CSV
        if CitationHelper.has_property(metadata, "row"):
            row = CitationHelper.get_string(metadata, "row")
            return f"{source}, dòng {row}" if row else source

        return source

    @staticmethod
    def build_full_citations(used_metadatas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        citations = []
        seen_identities = set()

        for metadata in used_metadatas:
            if not isinstance(metadata, dict):
                continue

            identity = CitationHelper.get_citation_identity(metadata)
            if identity in seen_identities:
                continue
            seen_identities.add(identity)

            # Copy and stringify properties
            dict_copy = {k: str(v) for k, v in metadata.items()}
            dict_copy["display_label"] = CitationHelper.build_citation_label(metadata)
            citations.append(dict_copy)

        return citations

    @staticmethod
    def build_footer(used_metadatas: List[Dict[str, Any]]) -> str:
        if not used_metadatas:
            return ""

        seen_identities = set()
        groups: List[FooterGroup] = []
        group_index: Dict[str, int] = {}

        for metadata in used_metadatas:
            if not isinstance(metadata, dict):
                continue

            identity = CitationHelper.get_citation_identity(metadata)
            if identity in seen_identities:
                continue
            seen_identities.add(identity)

            source = CitationHelper.get_string(metadata, "source") or "unknown"
            if source not in group_index:
                idx = len(groups)
                group_index[source] = idx
                groups.append(FooterGroup(source))
            else:
                idx = group_index[source]

            position_label = CitationHelper.build_position_label(metadata)
            if position_label:
                groups[idx].positions.append(FooterPosition(
                    label=position_label,
                    unit=CitationHelper.get_position_unit(metadata)
                ))

        if not groups:
            return ""

        file_parts = []
        files_taken = 0
        for group in groups:
            if files_taken >= CitationHelper.MaxFooterFiles:
                break
            files_taken += 1

            if not group.positions:
                file_parts.append(f'"{group.source}"')
                continue

            shown_positions = group.positions[:CitationHelper.MaxFooterPositionsPerFile]
            remaining = len(group.positions) - len(shown_positions)

            position_labels = [p.label for p in shown_positions]
            position_text = ", ".join(position_labels)

            if remaining > 0:
                unit = CitationHelper.get_dominant_unit(group.positions)
                position_text += f" và {remaining} {unit} khác"

            file_parts.append(f'"{group.source}", {position_text}')

        if not file_parts:
            return ""

        joined = "; ".join(file_parts)
        return f"\n\nNguồn: {joined}. Bạn có thể tìm đọc nếu muốn biết chi tiết hơn."

    @staticmethod
    def build_position_label(metadata: Dict[str, Any]) -> str:
        doc_type = CitationHelper.get_string(metadata, "type") or ""

        # PDF
        if doc_type.lower().startswith("pdf") or CitationHelper.has_property(metadata, "page"):
            if not doc_type.lower().startswith("pptx") and not CitationHelper.has_property(metadata, "slide"):
                page = CitationHelper.get_string(metadata, "page")
                return f"trang {page}" if page else ""

        # PPTX
        if doc_type.lower().startswith("pptx") or CitationHelper.has_property(metadata, "slide"):
            slide = CitationHelper.get_string(metadata, "slide")
            return f"slide {slide}" if slide else ""

        # DOCX
        if doc_type.lower().startswith("docx"):
            page_title = CitationHelper.get_string(metadata, "page_title")
            if page_title and page_title.strip():
                truncated = (
                    page_title[:CitationHelper.MaxDocxTitleLength] + "..."
                    if len(page_title) > CitationHelper.MaxDocxTitleLength
                    else page_title
                )
                return f"mục \"{truncated}\""
            
            paragraph_index = CitationHelper.get_string(metadata, "paragraph_index")
            if paragraph_index and paragraph_index.strip():
                return f"đoạn {paragraph_index}"

        # XLSX/CSV
        if CitationHelper.has_property(metadata, "row"):
            row = CitationHelper.get_string(metadata, "row")
            return f"dòng {row}" if row else ""

        return ""

    @staticmethod
    def get_position_unit(metadata: Dict[str, Any]) -> str:
        doc_type = CitationHelper.get_string(metadata, "type") or ""

        if doc_type.lower().startswith("pdf") or CitationHelper.has_property(metadata, "page"):
            if not doc_type.lower().startswith("pptx") and not CitationHelper.has_property(metadata, "slide"):
                return "trang"

        if doc_type.lower().startswith("pptx") or CitationHelper.has_property(metadata, "slide"):
            return "slide"

        if doc_type.lower().startswith("docx"):
            page_title = CitationHelper.get_string(metadata, "page_title")
            return "mục" if page_title and page_title.strip() else "đoạn"

        if CitationHelper.has_property(metadata, "row"):
            return "dòng"

        return "phần"

    @staticmethod
    def get_dominant_unit(positions: List[FooterPosition]) -> str:
        if not positions:
            return "phần"

        distinct_units = list(set(p.unit for p in positions))
        if len(distinct_units) > 1:
            return "vị trí"
        return distinct_units[0]
