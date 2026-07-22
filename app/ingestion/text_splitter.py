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
