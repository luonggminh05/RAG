from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class IntentType(str, Enum):
    RAG = "rag"
    CHITCHAT = "chitchat"
    OUT_OF_SCOPE = "out_of_scope"


class RouterOutput(BaseModel):
    """Structured Output từ LLM Supervisor Router."""
    intent: IntentType = Field(
        description="Phân loại ý định: 'rag' (tra cứu chính sách, quy trình, tài liệu), 'chitchat' (xã giao, chào hỏi), 'out_of_scope' (ngoài phạm vi)",
    )
    confidence: float = Field(
        default=0.9,
        ge=0.0,
        le=1.0,
        description="Độ tin cậy của phân loại từ 0.0 đến 1.0",
    )
    reasoning: str = Field(
        default="",
        description="Lý giải ngắn gọn căn cứ phân loại",
    )
    rewritten_query: Optional[str] = Field(
        default=None,
        description="Câu truy vấn độc lập ngữ cảnh nếu cần làm rõ",
    )
