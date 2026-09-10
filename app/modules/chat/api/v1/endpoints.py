import logging
import httpx
from typing import Optional, List
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.core.config import settings, AVAILABLE_MODELS
from app.modules.chat.api.v1.schemas import (
    ChatRequest,
    CreateConversationRequest,
    UpdateConversationTitleRequest,
    ConversationResponse,
    ChatMessageResponse,
    ModelItemResponse,
    ModelListResponse,
    FeedbackRequest,
    FeedbackResponse,
)
from app.modules.chat.service import ChatService
from app.modules.chat.repository import ChatRepository
from app.routers.dependencies import get_chat_service, get_chat_repository
from app.llmops.langfuse import log_feedback_score

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/models", response_model=ModelListResponse)
async def list_available_models():
    """
    Lấy danh sách các mô hình AI khả dụng, kiểm tra trạng thái thực tế từ Ollama.
    Route hiệu quả: GET /api/v1/chat/models
    """
    pulled_model_names = set()
    ollama_endpoint = getattr(settings, "llm_endpoint", "http://localhost:11434/v1")
    # Base url: e.g. http://localhost:11434
    base_ollama = ollama_endpoint.replace("/v1", "").rstrip("/")
    tags_url = f"{base_ollama}/api/tags"

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            res = await client.get(tags_url)
            if res.status_code == 200:
                data = res.json()
                for m in data.get("models", []):
                    name = m.get("name", "")
                    pulled_model_names.add(name.lower())
                    pulled_model_names.add(name.split(":")[0].lower())
    except Exception as ex:
        logger.debug(f"[MODELS] Could not fetch tags from Ollama at {tags_url}: {ex}")

    model_items = []
    for m in AVAILABLE_MODELS:
        m_id = m["id"]
        # Check if pulled or if ollama not responding we assume True to avoid blocking UI
        is_pulled = True
        if pulled_model_names:
            is_pulled = (m_id.lower() in pulled_model_names) or (m_id.split(":")[0].lower() in pulled_model_names)

        model_items.append(ModelItemResponse(
            id=m["id"],
            name=m["name"],
            type=m["type"],
            description=m["description"],
            is_available=is_pulled,
        ))

    default_model = getattr(settings, "llm_model_id", "qwen2.5vl:7b")
    return ModelListResponse(
        models=model_items,
        current_default=default_model,
    )


# Route hiệu quả: POST /api/v1/chat/stream
@router.post("/stream")
async def chat_stream(
    request: ChatRequest,
    x_user_roles: Optional[str] = Header(None, alias="X-User-Roles"),
    x_user_department: Optional[str] = Header(None, alias="X-User-Department"),
    chat_service: ChatService = Depends(get_chat_service),
):
    roles = request.user_roles or x_user_roles
    dept = request.user_department or x_user_department

    generator = chat_service.stream_chat(
        message=request.message,
        images=request.images,
        user_roles=roles,
        user_department=dept,
        conversation_id=request.conversation_id,
        user_id=request.user_id,
        model=request.model,
        enable_vision=request.enable_vision,
        top_k=request.top_k,
        is_retry=request.is_retry,
        retry_message_id=request.retry_message_id,
    )

    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/conversations", response_model=ConversationResponse)
async def create_conversation(
    request: CreateConversationRequest,
    repository: ChatRepository = Depends(get_chat_repository),
):
    conv_id = repository.create_conversation(user_id=request.user_id, title=request.title or "Cuộc hội thoại mới")
    conv = repository.get_conversation(conv_id)
    if not conv:
        raise HTTPException(status_code=500, detail="Failed to retrieve created conversation.")
    return conv


@router.get("/conversations", response_model=List[ConversationResponse])
async def list_conversations(
    user_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    pinned_only: bool = Query(False),
    repository: ChatRepository = Depends(get_chat_repository),
):
    return repository.list_conversations(user_id=user_id, limit=limit, offset=offset, pinned_only=pinned_only)


@router.get("/conversations/{id}", response_model=ConversationResponse)
async def get_conversation(
    id: int,
    user_id: Optional[str] = Query(None),
    repository: ChatRepository = Depends(get_chat_repository),
):
    conv = repository.get_conversation(id, user_id=user_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return conv


@router.put("/conversations/{id}/title")
async def update_conversation_title(
    id: int,
    request: UpdateConversationTitleRequest,
    repository: ChatRepository = Depends(get_chat_repository),
):
    repository.update_conversation_title(id, request.title)
    return {"status": "success"}


@router.delete("/conversations/{id}")
async def delete_conversation(
    id: int,
    repository: ChatRepository = Depends(get_chat_repository),
):
    success = repository.delete_conversation(id)
    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found or could not be deleted.")
    return {"status": "success", "message": f"Conversation {id} deleted."}


@router.get("/conversations/{id}/messages", response_model=List[ChatMessageResponse])
async def get_conversation_messages(
    id: int,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    repository: ChatRepository = Depends(get_chat_repository),
):
    return repository.get_messages(id, limit=limit, offset=offset)


@router.post("/messages/{message_id}/feedback", response_model=FeedbackResponse)
@router.post("/{message_id}/feedback", response_model=FeedbackResponse)
async def submit_message_feedback(
    message_id: int,
    request: FeedbackRequest,
    repository: ChatRepository = Depends(get_chat_repository),
):
    """
    Tiếp nhận phản hồi của người dùng (Like / Dislike) cho tin nhắn AI,
    lưu vào CSDL và đồng bộ điểm đánh giá lên Langfuse Tracing Dashboard.
    """
    rating_clean = request.rating.lower().strip()
    if rating_clean not in ("positive", "negative", "like", "dislike"):
        raise HTTPException(status_code=400, detail="Rating must be 'positive' or 'negative'.")

    normalized_rating = "positive" if rating_clean in ("positive", "like") else "negative"
    score_val = 1.0 if normalized_rating == "positive" else 0.0

    try:
        fb_id = repository.add_feedback(
            message_id=message_id,
            rating=normalized_rating,
            comment=request.comment,
        )
        # Log to Langfuse
        log_feedback_score(
            name="user_feedback",
            value=score_val,
            comment=request.comment,
            observation_id=str(message_id),
        )
        return FeedbackResponse(
            id=fb_id,
            message_id=message_id,
            rating=normalized_rating,
            status="success",
        )
    except Exception as ex:
        logger.error(f"[FEEDBACK] Error saving feedback for message={message_id}: {ex}")
        raise HTTPException(status_code=500, detail=f"Failed to submit feedback: {str(ex)}")
