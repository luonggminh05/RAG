from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class ChatImageInput(BaseModel):
    fileName: str
    contentType: str
    base64: str

class ChatRequest(BaseModel):
    message: str = ""
    images: List[ChatImageInput] = Field(default_factory=list)
    user_roles: Optional[str] = Field(default=None, alias="user_roles")
    user_department: Optional[str] = Field(default=None, alias="user_department")
    conversation_id: Optional[str] = Field(default=None, alias="conversation_id")
    user_id: Optional[str] = Field(default=None, alias="user_id")
    model: Optional[str] = Field(default=None, description="Mô hình LLM tùy chọn (ví dụ: qwen2.5:3b, qwen2.5vl:7b, deepseek-r1:7b)")
    enable_vision: bool = Field(default=True, description="Bật/Tắt phân tích ảnh đính kèm")
    top_k: Optional[int] = Field(default=None, ge=1, le=50, description="Số lượng trích dẫn RAG tối đa")
    is_retry: bool = Field(default=False, description="Đánh dấu câu hỏi là retry/thử lại")
    retry_message_id: Optional[int] = Field(default=None, description="ID tin nhắn cần retry")
    is_edit: bool = Field(default=False, description="Đánh dấu câu hỏi là chỉnh sửa tin nhắn cũ")
    edit_message_id: Optional[int] = Field(default=None, description="ID tin nhắn user cần chỉnh sửa")

    model_config = {"populate_by_name": True}

class ModelItemResponse(BaseModel):
    id: str
    name: str
    type: str
    description: str
    is_available: bool = True

class ModelListResponse(BaseModel):
    models: List[ModelItemResponse]
    current_default: str

class CreateConversationRequest(BaseModel):
    title: Optional[str] = "Cuộc hội thoại mới"
    user_id: Optional[str] = None

class UpdateConversationTitleRequest(BaseModel):
    title: str

class ChatMessageResponse(BaseModel):
    id: int
    conversation_id: Optional[int]
    role: str
    content: str
    created_at: Optional[str]

class ConversationResponse(BaseModel):
    id: int
    user_id: Optional[str]
    title: str
    is_pinned: bool
    created_at: Optional[str]
    updated_at: Optional[str]

class FeedbackRequest(BaseModel):
    rating: str = Field(..., description="'positive' hoặc 'negative'")
    comment: Optional[str] = Field(default=None, description="Ý kiến đóng góp tùy chọn")

class FeedbackResponse(BaseModel):
    id: int
    message_id: int
    rating: str
    status: str = "success"

class TranscribeResponse(BaseModel):
    text: str
    status: str = "success"

