import docx
import re
from typing import List, Optional, Dict, Any
from app.ingestion.parsers.base import BaseDocumentParser
from app.ingestion.text_splitter import IngestedDocument
from app.ingestion.text_cleaner import TextArtifactCleaner
from app.ingestion.procedure_extractor import ProcedureBlockExtractor
from app.services.action_classifier import ActionKindClassifier

class ParsedParagraph:
    def __init__(self, index: int, text: str):
        self.index = index
        self.text = text

class ProcedureGroup:
    def __init__(self):
        self.title_paragraph: Optional[ParsedParagraph] = None
        self.paragraphs: List[ParsedParagraph] = []

class WordParser(BaseDocumentParser):
    def can_parse(self, extension: str) -> bool:
        return extension.lower() == ".docx"

    def _is_potential_heading(self, text: str) -> bool:
        if not text or not text.strip():
            return False
        trimmed = text.strip()
        if ProcedureBlockExtractor.is_step_line(trimmed):
            return False
        return 0 < len(trimmed) <= 150

    async def parse_async(self, file_path: str, file_name: str) -> List[IngestedDocument]:
        # python-docx file opening
        doc = docx.Document(file_path)
        
        parsed_paragraphs = []
        paragraph_index = 0

        # Extract paragraphs
        for paragraph in doc.paragraphs:
            paragraph_index += 1
            raw_text = paragraph.text
            # tab character in python-docx is already handled in raw_text, but let's make sure
            # we run CollapseIconGaps like C#
            line_text = TextArtifactCleaner.collapse_icon_gaps(raw_text)
            
            if line_text and line_text.strip():
                parsed_paragraphs.Add = ParsedParagraph(index=paragraph_index, text=line_text)
                parsed_paragraphs.append(parsed_paragraphs.Add)

        groups = []
        in_group = False
        current_group = None

        # Group steps into procedure blocks
        for i, p in enumerate(parsed_paragraphs):
            is_step = ProcedureBlockExtractor.is_step_line(p.text)
            # Check if it is Step 1 (starts a new procedure)
            is_step_1 = is_step and bool(re.search(r'\b(?:Bước|Buoc|Step|B)\s*1\b', p.text, re.IGNORECASE))

            if is_step:
                if is_step_1 or not in_group:
                    if current_group:
                        groups.append(current_group)
                    current_group = ProcedureGroup()
                    in_group = True
                    
                    # Check if the previous paragraph in document was a potential heading/title
                    if i > 0:
                        prev_p = parsed_paragraphs[i - 1]
                        if self._is_potential_heading(prev_p.text):
                            current_group.title_paragraph = prev_p
                            
                current_group.paragraphs.append(p)
            else:
                if in_group:
                    groups.append(current_group)
                    current_group = None
                    in_group = False

        if current_group:
            groups.append(current_group)

        # Mark indices consumed by groups to avoid duplicate processing in standard ui_details
        consumed = set()
        for g in groups:
            if g.title_paragraph:
                consumed.add(g.title_paragraph.index)
            for p in g.paragraphs:
                consumed.add(p.index)

        emitted_docs = []

        # 1. Process grouped procedures
        for g in groups:
            body_text = "\n".join(p.text for p in g.paragraphs)
            title = g.title_paragraph.text if g.title_paragraph else ""
            
            action_kind = ActionKindClassifier.determine_action_kind(title) or ActionKindClassifier.determine_action_kind(body_text)
            step_count = ProcedureBlockExtractor.count_steps(body_text)

            metadata = {
                "source": file_name,
                "type": "docx_text",
                "content_kind": "instruction_text",
                "instruction_role": "procedure_steps"
            }

            if g.title_paragraph:
                metadata["paragraph_index"] = g.title_paragraph.index
            elif g.paragraphs:
                metadata["paragraph_index"] = g.paragraphs[0].index

            if title:
                metadata["page_title"] = title
            if action_kind:
                metadata["action_kind"] = action_kind
            if step_count > 0:
                metadata["step_count"] = step_count

            prefix = f"[TRANG: {title}]\n" if title else ""
            emitted_docs.append(IngestedDocument(
                page_content=f"{prefix}[VĂN BẢN HƯỚNG DẪN]\n{body_text}",
                metadata=metadata
            ))

        # 2. Process non-consumed paragraphs (standard text info)
        for p in parsed_paragraphs:
            if p.index in consumed:
                continue

            if p.text and p.text.strip():
                detail_action = ActionKindClassifier.determine_action_kind(p.text)
                metadata = {
                    "source": file_name,
                    "type": "docx_text",
                    "content_kind": "instruction_text",
                    "instruction_role": "ui_details",
                    "paragraph_index": p.index
                }
                if detail_action:
                    metadata["action_kind"] = detail_action

                emitted_docs.append(IngestedDocument(
                    page_content=f"[VĂN BẢN HƯỚNG DẪN]\n{p.text}",
                    metadata=metadata
                ))

        # Sort documents by paragraph index
        emitted_docs.sort(key=lambda d: d.metadata.get("paragraph_index", 0))
        return emitted_docs
