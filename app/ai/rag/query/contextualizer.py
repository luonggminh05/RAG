import asyncio
import logging
import re
from typing import Any, Dict, List, Optional
from langchain_core.messages import HumanMessage, SystemMessage
from app.core.config import settings
from app.llmops.factory import get_chat_model

logger = logging.getLogger(__name__)

REWRITE_SYSTEM_PROMPT = (
    "Bạn là chuyên viên tối ưu hóa câu hỏi tìm kiếm cho hệ thống RAG (Retrieval-Augmented Generation).\n"
    "Nhiệm vụ: Dựa vào lịch sử hội thoại gần nhất và câu hỏi hiện tại của người dùng, nếu câu hỏi có chứa đại từ thay thế "
    "('nó', 'đó', 'bước này', 'ai duyệt', 'ở đâu'...) hoặc phụ thuộc ngữ cảnh trước đó, hãy viết lại thành MỘT CÂU HỎI ĐỘC LẬP "
    "đầy đủ ý nghĩa để công cụ tìm kiếm tài liệu có thể hiểu được.\n"
    "Quy tắc tuyệt đối:\n"
    "1. KHÔNG trả lời câu hỏi, CHỈ viết lại câu hỏi.\n"
    "2. Nếu câu hỏi đã độc lập và rõ nghĩa, hãy giữ nguyên nội dung gốc.\n"
    "3. Chỉ trả về duy nhất nội dung câu hỏi đã viết lại, không thêm giải thích hay dấu ngoặc kép."
)

class QueryContextualizer:
    """
    Query Contextualizer / Rewriter:
    Biến đổi câu hỏi tiếp nối của người dùng thành câu truy vấn độc lập ngữ nghĩa.
    Có cơ chế timeout và graceful fallback về câu hỏi gốc nếu gặp lỗi.
    """

    def __init__(self, model_id: Optional[str] = None, timeout: float = 1.8):
        self.model_id = model_id or getattr(settings, "llm_model_id", "qwen2.5:3b")
        self.timeout = timeout

    async def rewrite(
        self,
        query: str,
        history: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        clean_query = (query or "").strip()
        if not clean_query:
            return clean_query

        # Nếu không có lịch sử hội thoại, không cần rewrite
        if not history or len(history) == 0:
            return clean_query

        # Kiểm tra nhanh xem câu hỏi có dấu hiệu phụ thuộc ngữ cảnh không
        # Nếu câu hỏi quá dài (>120 ký tự) và không có từ nối, thường đã là câu độc lập
        has_followup_marker = bool(
            re.search(
                r"\b(nó|đó|kia|bước này|bước tiếp theo|sau đó|ở đâu|ai duyệt|tại sao|như thế nào|thế nào|còn gì|nữa không)\b",
                clean_query,
                re.IGNORECASE,
            )
        )
        if len(clean_query) > 120 and not has_followup_marker:
            return clean_query

        # Format 3 lượt trao đổi gần nhất
        recent_history = history[-4:]
        history_lines = []
        for turn in recent_history:
            role = turn.get("role", "")
            content = turn.get("content", "")
            if role in ("user", "assistant") and content:
                # Cắt ngắn nội dung nếu quá dài để tiết kiệm context
                snippet = content[:250].replace("\n", " ")
                history_lines.append(f"{role.capitalize()}: {snippet}")

        if not history_lines:
            return clean_query

        prompt_input = (
            f"LỊCH SỬ HỘI THOẠI:\n" + "\n".join(history_lines) + f"\n\nCÂU HỎI HIỆN TẠI:\n{clean_query}"
        )

        try:
            llm = get_chat_model(model=self.model_id)
            messages = [
                SystemMessage(content=REWRITE_SYSTEM_PROMPT),
                HumanMessage(content=prompt_input),
            ]

            response = await asyncio.wait_for(
                llm.ainvoke(messages),
                timeout=self.timeout,
            )

            rewritten = (
                response.content
                if hasattr(response, "content")
                else str(response)
            ).strip().strip("\"'").replace("\n", " ")

            if rewritten and len(rewritten) >= 3:
                logger.info(f"[REWRITER] Rewrote query: '{clean_query}' -> '{rewritten}'")
                return rewritten
            return clean_query

        except asyncio.TimeoutError:
            logger.debug(f"[REWRITER] Timeout ({self.timeout}s) rewriting query. Fallback to original.")
            return clean_query
        except Exception as ex:
            logger.warning(f"[REWRITER] Failed to rewrite query: {ex}. Fallback to original.")
            return clean_query
