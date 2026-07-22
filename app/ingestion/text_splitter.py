import hashlib
import datetime
from typing import List, Dict, Any

class IngestedDocument:
    def __init__(self, page_content: str, metadata: Dict[str, Any]):
        self.page_content = page_content
        self.metadata = metadata

    def to_dict(self) -> Dict[str, Any]:
        return {
            "page_content": self.page_content,
            "metadata": self.metadata
        }

class SemanticChunker:
    """
    Token-aware Semantic Chunker that groups paragraphs and headings
    into cohesive chunks between min_tokens and max_tokens (e.g. 300-500 tokens).
    """

    @staticmethod
    def _count_tokens(text: str) -> int:
        try:
            import tiktoken
            encoding = tiktoken.get_encoding("cl100k_base")
            return len(encoding.encode(text))
        except ImportError:
            # Fallback estimation: average 1.3 tokens per word for Vietnamese/English mix
            words = len(text.split())
            return int(words * 1.3)

    @classmethod
    def split_documents(
        cls,
        documents: List[IngestedDocument],
        min_tokens: int = 300,
        max_tokens: int = 500,
        overlap_tokens: int = 75
    ) -> List[IngestedDocument]:
        result = []

        for doc in documents:
            text = doc.page_content
            if not text or not text.strip():
                continue

            total_tokens = cls._count_tokens(text)
            if total_tokens <= max_tokens:
                result.append(doc)
                continue

            # Split into structural blocks (paragraphs / headings)
            blocks = [b.strip() for b in text.split('\n\n') if b.strip()]
            if not blocks:
                blocks = [b.strip() for b in text.split('\n') if b.strip()]

            current_chunk_blocks = []
            current_chunk_tokens = 0

            for block in blocks:
                block_tokens = cls._count_tokens(block)

                # If single block exceeds max_tokens, split it by character/words fallback
                if block_tokens > max_tokens:
                    if current_chunk_blocks:
                        chunk_text = "\n\n".join(current_chunk_blocks).strip()
                        if chunk_text:
                            result.append(IngestedDocument(page_content=chunk_text, metadata=dict(doc.metadata)))
                        current_chunk_blocks = []
                        current_chunk_tokens = 0

                    # Character fallback for enormous single block
                    sub_docs = TextSplitter.split_documents([IngestedDocument(block, dict(doc.metadata))], max_tokens * 4, overlap_tokens * 4)
                    result.extend(sub_docs)
                    continue

                if current_chunk_tokens + block_tokens > max_tokens and current_chunk_tokens >= min_tokens:
                    # Emit current chunk
                    chunk_text = "\n\n".join(current_chunk_blocks).strip()
                    if chunk_text:
                        result.append(IngestedDocument(page_content=chunk_text, metadata=dict(doc.metadata)))
                    
                    # Prepare overlap blocks
                    overlap_blocks = []
                    overlap_count = 0
                    for b in reversed(current_chunk_blocks):
                        b_tok = cls._count_tokens(b)
                        if overlap_count + b_tok <= overlap_tokens:
                            overlap_blocks.insert(0, b)
                            overlap_count += b_tok
                        else:
                            break
                    
                    current_chunk_blocks = overlap_blocks + [block]
                    current_chunk_tokens = overlap_count + block_tokens
                else:
                    current_chunk_blocks.append(block)
                    current_chunk_tokens += block_tokens

            # Emit remaining block chunk
            if current_chunk_blocks:
                chunk_text = "\n\n".join(current_chunk_blocks).strip()
                if chunk_text:
                    result.append(IngestedDocument(page_content=chunk_text, metadata=dict(doc.metadata)))

        return result

class TextSplitter:
    @staticmethod
    def split_documents(documents: List[IngestedDocument], chunk_size: int, chunk_overlap: int) -> List[IngestedDocument]:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be > 0")
        if chunk_overlap < 0:
            raise ValueError("chunk_overlap must be >= 0")
        if chunk_overlap > chunk_size // 2:
            raise ValueError("chunk_overlap must be <= chunk_size // 2")

        result = []

        for doc in documents:
            text = doc.page_content
            if not text or not text.strip():
                continue

            if len(text) <= chunk_size:
                result.append(doc)
                continue

            current_idx = 0
            while current_idx < len(text):
                target_length = min(chunk_size, len(text) - current_idx)
                actual_length = target_length

                baseline_advance = chunk_size - chunk_overlap
                min_advance = max(baseline_advance // 4, 1)

                # Try to find a space to break on if we are not at the end
                if current_idx + target_length < len(text):
                    # Last space in the overlap region
                    overlap_start = current_idx + target_length - chunk_overlap
                    overlap_end = current_idx + target_length
                    overlap_region = text[overlap_start:overlap_end]
                    
                    last_space_in_overlap = overlap_region.rfind(' ')
                    if last_space_in_overlap != -1:
                        last_space = overlap_start + last_space_in_overlap
                        if last_space > current_idx:
                            candidate_length = last_space - current_idx
                            if candidate_length >= chunk_overlap + min_advance:
                                actual_length = candidate_length

                chunk_text = text[current_idx:current_idx + actual_length].strip()
                if chunk_text:
                    # Copy metadata to avoid reference sharing
                    new_metadata = dict(doc.metadata)
                    result.append(IngestedDocument(
                        page_content=chunk_text,
                        metadata=new_metadata
                    ))

                if current_idx + actual_length >= len(text):
                    break

                advance = max(actual_length - chunk_overlap, min_advance)
                current_idx += advance

        return result

    @staticmethod
    def generate_chunk_id(relative_path: str, last_write_time_utc: datetime.datetime, length: int, index: int) -> str:
        # Standard ticks calculation matching C# DateTime.Ticks
        if last_write_time_utc.tzinfo is None:
            # Assume UTC if naive
            last_write_time_utc = last_write_time_utc.replace(tzinfo=datetime.timezone.utc)
        
        epoch = datetime.datetime(1, 1, 1, tzinfo=datetime.timezone.utc)
        delta = last_write_time_utc - epoch
        ticks = int(delta.total_seconds() * 10_000_000)

        input_str = f"{relative_path}|{ticks}|{length}"
        sha256 = hashlib.sha256(input_str.encode('utf-8')).hexdigest()
        return f"{sha256}_chunk_{index}"
