import docx
import re
from typing import List, Optional
from app.ai.rag.ingestion.parsers.base import BaseDocumentParser, IngestedDocument
from app.ai.rag.text.text_cleaner import TextArtifactCleaner
from app.ai.rag.ingestion.procedure_extractor import ProcedureBlockExtractor
from app.shared.utils.action_classifier import ActionKindClassifier

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
        return extension.lower() in [".docx", ".doc"]

    def _is_potential_heading(self, text: str) -> bool:
        if not text or not text.strip():
            return False
        trimmed = text.strip()
        if ProcedureBlockExtractor.is_step_line(trimmed):
            return False
        return 0 < len(trimmed) <= 150

    async def parse_async(self, file_path: str, file_name: str) -> List[IngestedDocument]:
        try:
            doc = docx.Document(file_path)
            raw_paragraphs = [p.text for p in doc.paragraphs]
        except Exception:
            raw_paragraphs = []
            try:
                import zipfile
                with zipfile.ZipFile(file_path) as z:
                    if "word/document.xml" in z.namelist():
                        xml_content = z.read("word/document.xml").decode("utf-8", errors="replace")
                        extracted_texts = re.findall(r'<w:t[^>]*>(.*?)</w:t>', xml_content)
                        if extracted_texts:
                            raw_paragraphs = extracted_texts
            except Exception:
                pass

            if not raw_paragraphs:
                try:
                    with open(file_path, "rb") as f:
                        content = f.read().decode("utf-8", errors="replace")
                        cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', content)
                        raw_paragraphs = [cleaned]
                except Exception:
                    raw_paragraphs = []

        parsed_paragraphs = []
        paragraph_index = 0
        for raw_text in raw_paragraphs:
            paragraph_index += 1
            line_text = TextArtifactCleaner.collapse_icon_gaps(raw_text)
            if line_text and line_text.strip():
                parsed_paragraphs.append(ParsedParagraph(index=paragraph_index, text=line_text))

        groups = []
        in_group = False
        current_group = None

        for i, p in enumerate(parsed_paragraphs):
            is_step = ProcedureBlockExtractor.is_step_line(p.text)
            is_step_1 = is_step and bool(re.search(r'\b(?:Bước|Buoc|Step|B)\s*1\b', p.text, re.IGNORECASE))

            if is_step:
                if is_step_1 or not in_group:
                    if current_group:
                        groups.append(current_group)
                    current_group = ProcedureGroup()
                    in_group = True
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

        if in_group and current_group:
            groups.append(current_group)

        emitted_docs = []
        for g in groups:
            combined_text = "\n".join([p.text for p in g.paragraphs])
            action_kind = ActionKindClassifier.determine_action_kind(combined_text)
            if not action_kind and g.title_paragraph:
                action_kind = ActionKindClassifier.determine_action_kind(g.title_paragraph.text)

            step_count = len([p for p in g.paragraphs if ProcedureBlockExtractor.is_step_line(p.text)])
            page_title = g.title_paragraph.text.strip() if g.title_paragraph else None

            page_content = (
                f"[MỤC: {page_title}]\n[VĂN BẢN HƯỚNG DẪN]\n{combined_text}"
                if page_title else
                f"[VĂN BẢN HƯỚNG DẪN]\n{combined_text}"
            )

            metadata = {
                "source": file_name,
                "paragraph_index": g.paragraphs[0].index if g.paragraphs else 1,
                "type": "docx_procedure",
                "content_kind": "instruction_text",
                "instruction_role": "procedure_steps",
                "step_count": step_count
            }
            if page_title:
                metadata["page_title"] = page_title
            if action_kind:
                metadata["action_kind"] = action_kind

            emitted_docs.append(IngestedDocument(page_content=page_content, metadata=metadata))

        # Fallback for plain non-step documents
        if not emitted_docs and parsed_paragraphs:
            full_text = "\n".join([p.text for p in parsed_paragraphs])
            emitted_docs.append(IngestedDocument(
                page_content=full_text,
                metadata={"source": file_name, "type": "docx_text", "content_kind": "instruction_text"}
            ))

        return emitted_docs
