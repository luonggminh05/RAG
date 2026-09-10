import abc
import re
from typing import Any, Dict, List, Optional

class BaseMetric(abc.ABC):
    name: str = "base_metric"
    description: str = ""

    @abc.abstractmethod
    async def evaluate(self, case: Dict[str, Any], output: Dict[str, Any]) -> float:
        """Đánh giá và trả về điểm số từ 0.0 đến 1.0 (hoặc giá trị đo lường)."""
        pass


class HitRateAtK(BaseMetric):
    """
    Hit Rate @ K:
    Tỷ lệ queries có ít nhất 1 chunk liên quan trong top-K kết quả tra cứu.
    Điểm = 1.0 nếu có ít nhất 1 chunk khớp từ khóa mong đợi, ngược lại = 0.0.
    """
    name = "hit_rate_at_k"
    description = "Tỷ lệ có ít nhất 1 chunk đúng trong top-K kết quả"

    def __init__(self, k: int = 5):
        self.k = k

    async def evaluate(self, case: Dict[str, Any], output: Dict[str, Any]) -> float:
        documents: List[str] = output.get("documents", [])[:self.k]
        expected_keywords: List[str] = case.get("expected_source_keywords", [])
        expected_sources: List[str] = case.get("expected_sources", [])

        if not documents:
            return 0.0

        if not expected_keywords and not expected_sources:
            return 1.0

        citations = output.get("citations", [])[:self.k]

        for idx, doc in enumerate(documents):
            doc_lower = doc.lower()
            # Kiểm tra khớp từ khóa
            for kw in expected_keywords:
                if kw.lower() in doc_lower:
                    return 1.0
            # Kiểm tra nguồn tài liệu
            if idx < len(citations):
                cit = citations[idx]
                src = (cit.get("source") or cit.get("file_name") or "").lower()
                for exp_src in expected_sources:
                    if exp_src.lower() in src:
                        return 1.0

        return 0.0


class MRRAtK(BaseMetric):
    """
    Mean Reciprocal Rank @ K:
    Đo vị trí xếp hạng của chunk đúng đầu tiên (1 / rank).
    Nếu chunk đầu tiên đúng -> 1.0. Nếu chunk thứ 2 đúng -> 0.5. Không tìm thấy -> 0.0.
    """
    name = "mrr_at_k"
    description = "Mean Reciprocal Rank của chunk đúng đầu tiên"

    def __init__(self, k: int = 5):
        self.k = k

    async def evaluate(self, case: Dict[str, Any], output: Dict[str, Any]) -> float:
        documents: List[str] = output.get("documents", [])[:self.k]
        expected_keywords: List[str] = case.get("expected_source_keywords", [])
        expected_sources: List[str] = case.get("expected_sources", [])

        if not documents or (not expected_keywords and not expected_sources):
            return 0.0

        citations = output.get("citations", [])[:self.k]

        for rank, doc in enumerate(documents, start=1):
            doc_lower = doc.lower()
            matched = False
            for kw in expected_keywords:
                if kw.lower() in doc_lower:
                    matched = True
                    break
            if not matched and rank - 1 < len(citations):
                cit = citations[rank - 1]
                src = (cit.get("source") or cit.get("file_name") or "").lower()
                for exp_src in expected_sources:
                    if exp_src.lower() in src:
                        matched = True
                        break
            if matched:
                return round(1.0 / rank, 4)

        return 0.0


class ContextRelevanceScore(BaseMetric):
    """
    Context Relevance Score:
    Tỷ lệ số lượng chunks thực sự liên quan trên tổng số chunks được trả về.
    """
    name = "context_relevance"
    description = "Tỷ lệ chunk liên quan trên tổng số chunks retrieved"

    async def evaluate(self, case: Dict[str, Any], output: Dict[str, Any]) -> float:
        documents: List[str] = output.get("documents", [])
        expected_keywords: List[str] = case.get("expected_source_keywords", [])

        if not documents:
            return 0.0
        if not expected_keywords:
            return 1.0

        relevant_count = 0
        for doc in documents:
            doc_lower = doc.lower()
            if any(kw.lower() in doc_lower for kw in expected_keywords):
                relevant_count += 1

        return round(relevant_count / len(documents), 4)


class FaithfulnessScore(BaseMetric):
    """
    Faithfulness Score:
    Đo lường mức độ trung thực của câu trả lời dựa trên context và các từ khóa cốt lõi.
    Tỷ lệ các từ khóa nghiệp vụ mong đợi xuất hiện trong câu trả lời.
    """
    name = "faithfulness"
    description = "Mức độ trung thực và bao hàm thông tin ngữ cảnh"

    async def evaluate(self, case: Dict[str, Any], output: Dict[str, Any]) -> float:
        answer = str(output.get("answer", "") or output.get("final_answer", "")).lower()
        expected_keywords: List[str] = case.get("expected_answer_keywords", [])

        if not answer:
            return 0.0
        if not expected_keywords:
            return 1.0

        matched = sum(1 for kw in expected_keywords if kw.lower() in answer)
        return round(matched / len(expected_keywords), 4)


class HallucinationRate(BaseMetric):
    """
    Hallucination Rate:
    Tỷ lệ thông tin bịa đặt hoặc xuất hiện các từ khóa cấm / lạc đề.
    Điểm 0.0 = Hoàn hảo (không bịa đặt), Điểm 1.0 = Bịa đặt hoàn toàn.
    """
    name = "hallucination_rate"
    description = "Tỷ lệ thông tin bịa đặt không có trong tài liệu"

    async def evaluate(self, case: Dict[str, Any], output: Dict[str, Any]) -> float:
        answer = str(output.get("answer", "") or output.get("final_answer", "")).lower()
        should_not_contain: List[str] = case.get("should_not_contain", [])

        if not answer:
            return 0.0
        if not should_not_contain:
            return 0.0

        found_forbidden = sum(1 for term in should_not_contain if term.lower() in answer)
        return round(min(1.0, found_forbidden / len(should_not_contain)), 4)


class CitationPrecision(BaseMetric):
    """
    Citation Precision:
    Kiểm tra tính chính xác và đầy đủ của trích dẫn (file_name, page/slide).
    """
    name = "citation_precision"
    description = "Độ chính xác và đầy đủ của thông tin trích dẫn"

    async def evaluate(self, case: Dict[str, Any], output: Dict[str, Any]) -> float:
        citations: List[Dict[str, Any]] = output.get("citations", [])
        if not citations:
            return 0.0

        valid_count = 0
        for cit in citations:
            if isinstance(cit, dict):
                has_source = bool(cit.get("source") or cit.get("file_name"))
                if has_source:
                    valid_count += 1

        return round(valid_count / len(citations), 4)


class AnswerLatency(BaseMetric):
    """
    Answer Latency:
    Đo thời gian hoàn tất xử lý (giây).
    """
    name = "latency_seconds"
    description = "Thời gian phản hồi tổng cộng (giây)"

    async def evaluate(self, case: Dict[str, Any], output: Dict[str, Any]) -> float:
        return float(round(output.get("latency_seconds", 0.0), 3))
