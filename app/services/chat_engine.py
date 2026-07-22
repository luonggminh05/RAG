import re
import json
import logging
from typing import List, Dict, Any, Tuple, Optional
from openai import AsyncOpenAI
from app.config import settings
from app.data.sql_repository import SqlDocumentRepository
from app.services.tei_embedding import TeiEmbeddingService
from app.services.query_classifier import QueryClassifier, QueryIntent
from app.services.action_classifier import ActionKindClassifier
from app.services.citation_helper import CitationHelper
from app.ingestion.text_cleaner import TextArtifactCleaner

logger = logging.getLogger(__name__)

class ChatEngine:
    def __init__(self, repository: SqlDocumentRepository, embedding_service: TeiEmbeddingService):
        self.repository = repository
        self.embedding_service = embedding_service
        # Initialize AsyncOpenAI client
        self.openai_client = AsyncOpenAI(
            base_url=settings.llm_endpoint,
            api_key=settings.llm_api_key
        )
        # In-memory chat memory (similar to ChatHub _chatMemory)
        self._chat_memory: Dict[str, str] = {}

    def get_last_lookup_key(self, connection_id: str) -> str:
        return f"chat:last-lookup:{connection_id}"

    def resolve_follow_up_message(self, message: str, connection_id: str) -> str:
        normalized = ActionKindClassifier.normalize_text(message)
        key = self.get_last_lookup_key(connection_id)
        if normalized in ["cua ai", "cua ai vay", "la cua ai", "ai vay"] and key in self._chat_memory:
            last_lookup = self._chat_memory[key]
            if last_lookup:
                return f"{last_lookup} là của ai"
        return message

    def remember_lookup_target(self, message: str, connection_id: str):
        doc_id = self.find_identifier(message)
        if doc_id:
            key = self.get_last_lookup_key(connection_id)
            self._chat_memory[key] = doc_id

    @staticmethod
    def is_simple_greeting(message: str) -> bool:
        normalized = ActionKindClassifier.normalize_text(message)
        return normalized in ["hi", "hello", "xin chao", "chao", "alo", "a lo"]

    @staticmethod
    def is_structured_lookup(message: str) -> bool:
        normalized = ActionKindClassifier.normalize_text(message)
        return (
            ChatEngine.find_identifier(message) is not None
            or any(val in normalized for val in ["mssv", "ma so id", "ma id", "ma so sinh vien", "email", "mail", "thu dien tu", "lop", "cua ai"])
        )

    @staticmethod
    def find_identifier(text: str) -> Optional[str]:
        match = re.search(r'\b\d{6,}\b', text)
        return match.group(0) if match else None

    @staticmethod
    def extract_person_name(text: str) -> Optional[str]:
        # C# Pattern 1
        match = re.search(
            r'(?:email|mail|thư điện tử)\s+(?:của|cua)\s+(.+?)(?:\s+(?:là|la)\s+gì|[?\uff1f])?$',
            text,
            re.IGNORECASE
        )
        if match:
            return match.group(1).strip()

        # C# Pattern 2
        match = re.search(r'(?:của|cua)\s+(.+?)(?:\s+(?:là|la)\s+gì|[?\uff1f])?$', text, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            norm = ActionKindClassifier.normalize_text(name)
            if norm not in ["ai", "ai vay"]:
                return name
        return None

    def determine_top_k(self, message: str) -> int:
        if self.is_structured_lookup(message):
            top_k = 100
        elif ActionKindClassifier.has_action_intent(message) or QueryClassifier.classify(message) == QueryIntent.TaskInstruction:
            top_k = 20
        else:
            top_k = settings.search_chat_top_k
        return max(1, min(top_k, settings.search_top_k_max))

    @staticmethod
    def is_procedure_steps(metadata: Dict[str, Any]) -> bool:
        return str(metadata.get("instruction_role", "")).lower() == "procedure_steps"

    @staticmethod
    def is_image_ui_description(metadata: Dict[str, Any]) -> bool:
        return str(metadata.get("content_kind", "")).lower() == "image_ui_description"

    @staticmethod
    def clean_context_chunk(document: str, line_occurrences: Dict[str, int]) -> str:
        return TextArtifactCleaner.clean(document, line_occurrences)

    @staticmethod
    def truncate_to_last_space(text: str, max_length: int) -> str:
        if len(text) <= max_length:
            return text
        truncated = text[:max_length]
        last_space = truncated.rfind(' ')
        if last_space > 0:
            truncated = truncated[:last_space]
        return truncated.rstrip()

    @staticmethod
    def contains_action_keyword(normalized_line: str, keyword: str) -> bool:
        # Boundary check
        pattern = rf"(?<!\w){re.escape(keyword)}(?!\w)"
        return bool(re.search(pattern, normalized_line, re.IGNORECASE))

    @staticmethod
    def chunk_matches_action(content: str, metadata: Dict[str, Any], query_action: str) -> bool:
        # Check action_kind
        prop_action = metadata.get("action_kind")
        if prop_action:
            val = ActionKindClassifier.normalize_action_kind(str(prop_action))
            if val:
                return val.lower() == query_action.lower()

        # Check slide_title
        slide_title = metadata.get("slide_title")
        if slide_title:
            title_action = ActionKindClassifier.determine_action_kind(str(slide_title))
            if title_action:
                return title_action.lower() == query_action.lower()

        # Check first 3 lines of content
        if content and content.strip():
            lines = [ActionKindClassifier.normalize_text(l) for l in content.splitlines() if l.strip()][:3]
            keyword = ActionKindClassifier.get_action_keyword(query_action)
            if keyword:
                for line in lines:
                    if ChatEngine.contains_action_keyword(line, keyword):
                        return True
        return False

    @staticmethod
    def chunk_matches_different_action(content: str, metadata: Dict[str, Any], query_action: str) -> bool:
        chunk_action = None
        
        prop_action = metadata.get("action_kind")
        if prop_action:
            chunk_action = ActionKindClassifier.normalize_action_kind(str(prop_action))

        if not chunk_action:
            slide_title = metadata.get("slide_title")
            if slide_title:
                chunk_action = ActionKindClassifier.determine_action_kind(str(slide_title))

        if chunk_action:
            return chunk_action.lower() != query_action.lower()

        # Check first 3 lines against other actions
        if content and content.strip():
            lines = [ActionKindClassifier.normalize_text(l) for l in content.splitlines() if l.strip()][:3]
            other_actions = [a for a in ActionKindClassifier.AllActionKinds if a.lower() != query_action.lower()]

            for other_action in other_actions:
                keyword = ActionKindClassifier.get_action_keyword(other_action)
                if keyword:
                    for line in lines:
                        if ChatEngine.contains_action_keyword(line, keyword):
                            return True
        return False

    def append_related_chunks(
        self,
        documents: List[str],
        metadatas: List[Dict[str, Any]],
        related_chunks: List[Tuple[str, Dict[str, Any]]]
    ):
        seen = set()
        for i, doc in enumerate(documents):
            meta = metadatas[i] if i < len(metadatas) else {}
            key = f"{ActionKindClassifier.normalize_text(doc)}|{CitationHelper.get_citation_identity(meta)}"
            seen.add(key)

        for doc, meta in related_chunks:
            if not doc or not doc.strip():
                continue
            key = f"{ActionKindClassifier.normalize_text(doc)}|{CitationHelper.get_citation_identity(meta)}"
            if key not in seen:
                seen.add(key)
                documents.append(doc)
                metadatas.append(meta)

    def process_chunk_group(
        self,
        input_chunks: List[Tuple[str, Dict[str, Any]]],
        block_header: Optional[str],
        chunk_number: int,
        line_occurrences: Dict[str, int],
        accepted_chunk_line_sets: List[Tuple[set, Dict[str, Any]]],
        existing_sections: List[str]
    ) -> Tuple[List[str], int]:
        block = []
        if block_header:
            block.append(f"=== {block_header} ===")

        for doc, meta in input_chunks:
            cleaned = self.clean_context_chunk(doc, line_occurrences)
            if not cleaned or not cleaned.strip():
                continue

            chunk_limit = 5000 if self.is_procedure_steps(meta) else (1500 if self.is_image_ui_description(meta) else 2000)
            if len(cleaned) > chunk_limit:
                logger.info(f"Truncated chunk exceeding {chunk_limit} chars. Original: {len(cleaned)}")
                cleaned = self.truncate_to_last_space(cleaned, chunk_limit)

            # Near duplicate check (85% line overlap)
            cleaned_lines = [l.strip() for l in cleaned.splitlines() if l.strip()]
            normalized_set = set(ActionKindClassifier.normalize_text(l) for l in cleaned_lines)
            
            is_near_duplicate = False
            if len(normalized_set) >= 4:
                for prev_set, prev_meta in accepted_chunk_line_sets:
                    if len(prev_set) < 4:
                        continue
                    intersection = len(normalized_set.intersection(prev_set))
                    overlap = intersection / max(len(normalized_set), len(prev_set))
                    if overlap >= 0.85:
                        source_a = CitationHelper.get_string(meta, "source")
                        source_b = CitationHelper.get_string(prev_meta, "source")
                        title_a = CitationHelper.get_string(meta, "slide_title") or CitationHelper.get_string(meta, "page_title")
                        title_b = CitationHelper.get_string(prev_meta, "slide_title") or CitationHelper.get_string(prev_meta, "page_title")
                        action_a = CitationHelper.get_string(meta, "action_kind")
                        action_b = CitationHelper.get_string(prev_meta, "action_kind")

                        if source_a == source_b and title_a == title_b and action_a == action_b:
                            is_near_duplicate = True
                            break

            if is_near_duplicate:
                continue

            # Length constraint check
            temp_chunk_number = chunk_number + 1
            source_label = CitationHelper.build_citation_label(meta)
            temp_block = list(block) + [f"[ĐOẠN {temp_chunk_number} - {source_label}]\n{cleaned}"]
            temp_sections = list(existing_sections) + ["\n\n".join(temp_block)]
            temp_context = "\n\n---\n\n".join(temp_sections)

            if len(temp_context) > 18000:
                logger.info("Discarded chunk because total context length would exceed 18000 chars.")
                continue

            chunk_number = temp_chunk_number
            block.append(f"[ĐOẠN {chunk_number} - {source_label}]\n{cleaned}")
            accepted_chunk_line_sets.append((normalized_set, meta))

        return block, chunk_number

    def build_context_text(self, documents: List[str], metadatas: List[Dict[str, Any]], intent: QueryIntent) -> Tuple[str, List[Dict[str, Any]]]:
        instruction_chunks = []
        image_chunks = []
        other_chunks = []
        seen_documents = set()

        for i, doc in enumerate(documents):
            meta = metadatas[i] if i < len(metadatas) else {}
            document_key = f"{ActionKindClassifier.normalize_text(doc)}|{CitationHelper.get_citation_identity(meta)}"
            if document_key in seen_documents:
                continue
            seen_documents.add(document_key)

            content_kind = str(meta.get("content_kind", "")).lower()
            if content_kind == "image_ui_description":
                image_chunks.append((doc, meta))
            elif content_kind == "instruction_text":
                instruction_chunks.append((doc, meta))
            else:
                other_chunks.append((doc, meta))

        sections = []
        chunk_number = 0

        # Prioritize based on query intent
        primary_chunks = image_chunks if intent == QueryIntent.UiLocation else instruction_chunks
        primary_label = "MO TA TRUC QUAN GIAO DIEN TU ANH" if intent == QueryIntent.UiLocation else "VAN BAN HUONG DAN THAO TAC"
        
        secondary_chunks = instruction_chunks if intent == QueryIntent.UiLocation else image_chunks
        secondary_label = "VAN BAN HUONG DAN THAO TAC" if intent == QueryIntent.UiLocation else "MO TA TRUC QUAN GIAO DIEN TU ANH"

        line_occurrences = {}
        accepted_chunk_line_sets = []

        if primary_chunks:
            block, chunk_number = self.process_chunk_group(
                primary_chunks, primary_label, chunk_number, line_occurrences, accepted_chunk_line_sets, sections
            )
            if len(block) > 1:
                sections.append("\n\n".join(block))

        if secondary_chunks:
            block, chunk_number = self.process_chunk_group(
                secondary_chunks, secondary_label, chunk_number, line_occurrences, accepted_chunk_line_sets, sections
            )
            if len(block) > 1:
                sections.append("\n\n".join(block))

        if other_chunks:
            block, chunk_number = self.process_chunk_group(
                other_chunks, None, chunk_number, line_occurrences, accepted_chunk_line_sets, sections
            )
            if block:
                sections.append("\n\n".join(block))

        text = "\n\n---\n\n".join(sections)
        used_metadatas = [x[1] for x in accepted_chunk_line_sets]
        return text, used_metadatas

    @staticmethod
    def parse_structured_row(document: str) -> Dict[str, str]:
        fields = {}
        # Simple split by comma outside quotes
        parts = []
        current = []
        in_quotes = False
        for ch in document:
            if ch == '"':
                in_quotes = not in_quotes
                current.append(ch)
            elif ch == ',' and not in_quotes:
                parts.append("".join(current).strip())
                current = []
            else:
                current.append(ch)
        if current:
            parts.append("".join(current).strip())

        for part in parts:
            separator_index = part.find(':')
            if separator_index <= 0 or separator_index == len(part) - 1:
                continue
            key = ActionKindClassifier.normalize_text(part[:separator_index])
            value = part[separator_index + 1:].strip()
            if key and key not in fields:
                fields[key] = value
        return fields

    @staticmethod
    def get_field(fields: Dict[str, str], aliases: List[str]) -> Optional[str]:
        normalized_aliases = [ActionKindClassifier.normalize_text(a) for a in aliases]
        for alias in normalized_aliases:
            if alias in fields:
                return fields[alias]
        for key, value in fields.items():
            if any(alias == key or alias in key for alias in normalized_aliases):
                return value
        return None

    def try_answer_from_structured_context(
        self,
        question: str,
        documents: List[str],
        metadatas: List[Dict[str, Any]]
    ) -> Tuple[Optional[str], List[Dict[str, Any]]]:
        normalized_question = ActionKindClassifier.normalize_text(question)
        doc_id = self.find_identifier(question)
        name_query = self.extract_person_name(question)

        asks_email = any(val in normalized_question for val in ["email", "mail", "thu dien tu"])
        asks_person = any(val in normalized_question for val in ["cua ai", "la ai", "mssv", "ma so id", "ma id", "ma so sinh vien"]) or (doc_id is not None)

        for i, doc in enumerate(documents):
            row = self.parse_structured_row(doc)
            if not row:
                continue

            student_id = self.get_field(row, ["ma so id", "mssv", "ma id", "ma so sinh vien", "ma sinh vien", "student id", "id"])
            last_name = self.get_field(row, ["ho", "last name", "surname"])
            first_name = self.get_field(row, ["ten", "first name", "given name"])
            
            full_name = self.get_field(row, ["ho ten", "hoten", "ten sinh vien", "name", "full name"])
            if not full_name and (last_name or first_name):
                parts = [p for p in [last_name, first_name] if p]
                full_name = " ".join(parts).strip()

            email = self.get_field(row, ["dia chi thu dien tu", "thu dien tu", "email", "mail", "e-mail"])
            class_name = self.get_field(row, ["lop", "class"])

            matches_id = doc_id and student_id and student_id.strip().lower() == doc_id.lower()
            matches_name = name_query and full_name and ActionKindClassifier.normalize_text(name_query) in ActionKindClassifier.normalize_text(full_name)

            is_match = False
            if doc_id:
                is_match = matches_id
            elif name_query:
                is_match = matches_name

            if not is_match:
                continue

            matched_metadata = metadatas[i] if i < len(metadatas) else {}

            if asks_email:
                ans = f"Email của {full_name or name_query} là {email}." if email else "Mình tìm thấy người này trong tài liệu nhưng chưa thấy email trong dòng dữ liệu."
                return ans, [matched_metadata] if matched_metadata else []

            if asks_person:
                parts = []
                if student_id:
                    parts.append(f"Mã số ID: {student_id}")
                if full_name:
                    parts.append(f"Họ tên: {full_name}")
                if email:
                    parts.append(f"Email: {email}")
                if class_name:
                    parts.append(f"Lớp: {class_name}")
                
                ans = ", ".join(parts) + "." if parts else "Mình chưa tìm thấy thông tin này trong tài liệu đã nạp."
                return ans, [matched_metadata] if matched_metadata else []

        if doc_id or name_query:
            return "Mình chưa tìm thấy thông tin này trong tài liệu đã nạp.", []

        return None, []

    @staticmethod
    def count_procedure_steps(text: str) -> int:
        return len(re.findall(r'\b(?:Bước|Buoc|B)\s*\d+\s*:', text, re.IGNORECASE))

    def determine_max_tokens(self, context_text: str) -> int:
        step_count = self.count_procedure_steps(context_text)
        if step_count > 0:
            return max(900, min(600 + step_count * 120, 1800))
        return 600

    @staticmethod
    def is_repetition_loop(text: str) -> bool:
        if len(text) < 100:
            return False

        # Check line repetitions (a line repeated 3 times)
        lines = [ActionKindClassifier.normalize_text(l).strip() for l in text.splitlines() if l.strip()]
        for line in lines:
            if lines.count(line) >= 3:
                return True

        # Check suffix repetitions
        normalized = ActionKindClassifier.normalize_text(re.sub(r'\s+', ' ', text))
        suffix_length = 40
        if len(normalized) >= suffix_length * 2:
            suffix = normalized[-suffix_length:]
            # Check occurrences
            if normalized.count(suffix) >= 2:
                return True

        # Check recent sentence repetitions
        sentences = [ActionKindClassifier.normalize_text(s).strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]
        long_sentences = [s for s in sentences if len(s) >= 35]
        if len(long_sentences) >= 4:
            last = long_sentences[-1]
            if long_sentences.count(last) >= 3:
                return True

        return False
