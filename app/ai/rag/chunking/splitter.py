import logging
import re
from dataclasses import dataclass, field
from typing import Any
from langchain_text_splitters import RecursiveCharacterTextSplitter
from app.core.config import settings

logger = logging.getLogger(__name__)

@dataclass
class ChunkResult:
    """Kết quả phân tách văn bản kèm theo metadata ngữ cảnh tiêu đề."""
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


class TextChunker:
    """Tách văn bản thành các chunks ngữ nghĩa sử dụng RecursiveCharacterTextSplitter và Heading Context Breadcrumbs."""

    _HEADING_PATTERN = re.compile(
        r"^(#{1,6}\s+|(?:[IVXLCDM]+\b(?:\.\d+)*\.?|\d+(?:\.\d+)*\.?)\s+)([^\n]+)",
        re.IGNORECASE,
    )

    def __init__(self, chunk_size: int | None = None, chunk_overlap: int | None = None):
        self.chunk_size = chunk_size or getattr(settings, "ingestion_chunk_size", 600)
        self.chunk_overlap = chunk_overlap or getattr(settings, "ingestion_chunk_overlap", 100)
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            separators=["\n\n", "\n", ".", " ", ""],
            length_function=len,
        )

    def split_text(self, text: str) -> list[str]:
        if not text or not text.strip():
            return []
        chunks = self.splitter.split_text(text)
        logger.debug(
            "[CHUNK] Split text (len=%d) into %d chunks (size=%d, overlap=%d)",
            len(text),
            len(chunks),
            self.chunk_size,
            self.chunk_overlap,
        )
        return chunks

    def split_markdown_with_context(self, text: str) -> list[ChunkResult]:
        """
        Phân tách văn bản Markdown có bảo toàn ngữ cảnh tiêu đề (Heading Context Breadcrumbs).
        Mỗi chunk sinh ra sẽ được tự động đính kèm tiền tố ngữ cảnh:
        [Ngữ cảnh: IV.3 Quản lý loại hàng hóa > IV.3.2 Quy tắc chung và ràng buộc]
        """
        if not text or not text.strip():
            return []

        lines = text.splitlines()
        sections: list[tuple[list[dict[str, Any]], list[str]]] = []
        stack: list[dict[str, Any]] = []
        current_lines: list[str] = []

        for line in lines:
            stripped = line.strip()
            m = self._HEADING_PATTERN.match(stripped)
            if m:
                if current_lines:
                    sections.append((list(stack), current_lines))
                    current_lines = []
                prefix, _ = m.groups()
                if prefix.startswith("#"):
                    level = len(prefix.strip())
                else:
                    level = max(1, prefix.strip().count("."))
                clean_heading = stripped.lstrip("#").strip()
                while stack and stack[-1]["level"] >= level:
                    stack.pop()
                stack.append({"level": level, "heading": clean_heading})
                current_lines.append(stripped)
            else:
                current_lines.append(line)

        if current_lines:
            sections.append((list(stack), current_lines))

        results: list[ChunkResult] = []
        for st, body_lines in sections:
            section_path = " > ".join(item["heading"] for item in st)
            section = st[-1]["heading"] if st else ""
            heading_level = st[-1]["level"] if st else 0
            raw_heading = st[-1]["heading"] if st else ""
            body_text = "\n".join(body_lines).strip()
            if not body_text:
                continue

            raw_chunks = self.splitter.split_text(body_text)
            for chunk in raw_chunks:
                chunk_str = chunk.strip()
                if not chunk_str:
                    continue
                if chunk_str.startswith("[Ngữ cảnh:"):
                    final_text = chunk_str
                elif section_path:
                    final_text = f"[Ngữ cảnh: {section_path}]\n{chunk_str}"
                else:
                    final_text = chunk_str

                results.append(
                    ChunkResult(
                        text=final_text,
                        metadata={
                            "section": section,
                            "section_path": section_path,
                            "heading_level": heading_level,
                            "raw_heading": raw_heading,
                        },
                    )
                )

        logger.debug(
            "[CHUNK] split_markdown_with_context generated %d enriched chunks.",
            len(results),
        )
        return results

    def split_hierarchical(
        self,
        text: str,
        parent_chunk_size: int = 1000,
        parent_chunk_overlap: int = 150,
        child_chunk_size: int = 300,
        child_chunk_overlap: int = 50,
    ) -> list[tuple[ChunkResult, ChunkResult]]:
        """
        Phân tách văn bản phân cấp Parent-Child (Hierarchical Chunking).
        Trả về danh sách các cặp (child_chunk, parent_chunk):
        - child_chunk: Dùng để embedding và vector search (độ tập trung ngữ nghĩa cao).
        - parent_chunk: Chứa ngữ cảnh đầy đủ truyền cho LLM khi child_chunk được truy xuất.
        """
        if not text or not text.strip():
            return []

        parent_splitter = RecursiveCharacterTextSplitter(
            chunk_size=parent_chunk_size,
            chunk_overlap=parent_chunk_overlap,
            separators=["\n\n", "\n", ".", " ", ""],
            length_function=len,
        )
        child_splitter = RecursiveCharacterTextSplitter(
            chunk_size=child_chunk_size,
            chunk_overlap=child_chunk_overlap,
            separators=["\n\n", "\n", ".", " ", ""],
            length_function=len,
        )

        parent_texts = parent_splitter.split_text(text)
        results: list[tuple[ChunkResult, ChunkResult]] = []

        for p_idx, p_text in enumerate(parent_texts):
            p_chunk = ChunkResult(
                text=p_text.strip(),
                metadata={"parent_idx": p_idx, "length": len(p_text)}
            )
            c_texts = child_splitter.split_text(p_text)
            for c_idx, c_text in enumerate(c_texts):
                c_clean = c_text.strip()
                if not c_clean:
                    continue
                c_chunk = ChunkResult(
                    text=c_clean,
                    metadata={
                        "parent_idx": p_idx,
                        "child_idx": c_idx,
                        "parent_content": p_chunk.text,
                    }
                )
                results.append((c_chunk, p_chunk))

        logger.debug(
            "[CHUNK] split_hierarchical generated %d (child, parent) pairs from %d parents.",
            len(results),
            len(parent_texts),
        )
        return results
