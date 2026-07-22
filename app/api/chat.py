import base64
import json
import logging
import asyncio
from fastapi import APIRouter, Depends, HTTPException, Header
from fastapi.responses import StreamingResponse
from typing import Optional
from app.config import settings
from app.models.api_models import ChatRequest, Citation
from app.services.chat_engine import ChatEngine
from app.services.query_classifier import QueryClassifier, QueryIntent
from app.services.action_classifier import ActionKindClassifier
from app.services.citation_helper import CitationHelper
from app.services.vision_service import VisionService
from app.dependencies import get_repository, get_embedding_service, get_vision_service
from app.data.sql_repository import SqlDocumentRepository
from app.services.tei_embedding import TeiEmbeddingService

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    x_user_roles: Optional[str] = Header(None, alias="X-User-Roles"),
    repository: SqlDocumentRepository = Depends(get_repository),
    embedding_service: TeiEmbeddingService = Depends(get_embedding_service),
    vision_service: VisionService = Depends(get_vision_service)
):
    chat_engine = ChatEngine(repository, embedding_service)
    connection_id = "http-session"

    async def sse_generator():
        try:
            message = request.message or ""
            base_query = message.strip()
            
            # Process screenshots / images if present
            screenshot_descriptions = []
            chat_already_started = False
            
            if request.images:
                # Limit validation
                if len(request.images) > 3:
                    yield "event: token\ndata: {\"text\": \"\\n[Lỗi: Chỉ gửi tối đa 3 ảnh cùng lúc]\"}\n\n"
                    yield "event: chat_ended\ndata: {}\n\n"
                    return

                total_bytes = 0
                decoded_images = []
                for img in request.images:
                    if not img.base64:
                        continue
                    
                    content_type = img.contentType.lower() if img.contentType else ""
                    if content_type not in ["image/png", "image/jpeg", "image/jpg", "image/webp"]:
                        yield "event: token\ndata: {\"text\": \"\\n[Lỗi: Chỉ hỗ trợ định dạng ảnh PNG, JPEG, WEBP]\"}\n\n"
                        yield "event: chat_ended\ndata: {}\n\n"
                        return

                    try:
                        base64_data = img.base64
                        if "," in base64_data:
                            base64_data = base64_data.split(",")[1]
                        img_bytes = base64.b64decode(base64_data)
                    except Exception:
                        yield "event: token\ndata: {\"text\": \"\\n[Lỗi giải mã hình ảnh base64]\"}\n\n"
                        yield "event: chat_ended\ndata: {}\n\n"
                        return

                    total_bytes += len(img_bytes)
                    if total_bytes > 5 * 1024 * 1024:
                        yield "event: token\ndata: {\"text\": \"\\n[Lỗi: Tổng dung lượng ảnh vượt quá giới hạn 5MB]\"}\n\n"
                        yield "event: chat_ended\ndata: {}\n\n"
                        return
                    
                    decoded_images.append(img_bytes)

                if decoded_images:
                    chat_already_started = True
                    yield "event: chat_started\ndata: {}\n\n"
                    yield "event: token\ndata: {\"text\": \"\\n*Đang phân tích hình ảnh...*\\n\\n\"}\n\n"
                    
                    # Generate visual descriptions concurrently
                    tasks = [vision_service.describe_screenshot(img_bytes, base_query) for img_bytes in decoded_images]
                    results = await asyncio.gather(*tasks)
                    for desc in results:
                        if desc and desc.strip():
                            screenshot_descriptions.append(desc)

            # Re-check queries after screenshot descriptions
            if not base_query and screenshot_descriptions:
                base_query = screenshot_descriptions[0]

            if not base_query:
                yield "event: token\ndata: {\"text\": \"Bạn chưa nhập câu hỏi và không có hình ảnh hợp lệ để mô tả.\"}\n\n"
                yield "event: chat_ended\ndata: {}\n\n"
                return

            # Check greeting (only when no image is present)
            if not screenshot_descriptions and ChatEngine.is_simple_greeting(base_query):
                if not chat_already_started:
                    yield "event: chat_started\ndata: {}\n\n"
                yield "event: citations\ndata: []\n\n"
                yield "event: token\ndata: {\"text\": \"Xin chào! Mình có thể giúp bạn hỏi đáp dựa trên tài liệu đã nạp.\"}\n\n"
                yield "event: chat_ended\ndata: {}\n\n"
                return

            effective_message = chat_engine.resolve_follow_up_message(base_query, connection_id)
            retrieval_query = effective_message
            if screenshot_descriptions:
                retrieval_query = f"{effective_message}\n" + "\n".join(screenshot_descriptions)
                
            classification_query = retrieval_query if screenshot_descriptions else effective_message

            # TopK selection and query classification
            requested_top_k = chat_engine.determine_top_k(classification_query)
            query_intent = QueryClassifier.classify(classification_query)
            
            primary_kind = "instruction_text" if query_intent == QueryIntent.TaskInstruction else (
                "image_ui_description" if query_intent == QueryIntent.UiLocation else None
            )
            related_kind = "image_ui_description" if query_intent == QueryIntent.TaskInstruction else (
                "instruction_text" if query_intent == QueryIntent.UiLocation else None
            )

            # Get user roles
            roles = request.user_roles or x_user_roles

            # 1. Embedding
            query_embedding, _ = await embedding_service.embed_query_cached(retrieval_query)

            # 2. Database retrieval with role/scope filtering
            search_results = repository.search(
                query=retrieval_query,
                query_embedding=query_embedding,
                top_k=requested_top_k,
                content_kind=primary_kind,
                user_roles=roles
            )

            documents = search_results["documents"][0] if search_results["documents"] else []
            metadatas = search_results["metadatas"][0] if search_results["metadatas"] else []

            # Retry search without primary kind if no chunks retrieved
            if not documents and primary_kind:
                search_results = repository.search(
                    query=retrieval_query,
                    query_embedding=query_embedding,
                    top_k=requested_top_k,
                    user_roles=roles
                )
                documents = search_results["documents"][0] if search_results["documents"] else []
                metadatas = search_results["metadatas"][0] if search_results["metadatas"] else []

            # Fetch related chunks
            if related_kind and metadatas:
                limit = max(1, min(settings.search_chat_top_k, 10))
                related_chunks = repository.get_related_chunks(metadatas, related_kind, limit)
                chat_engine.append_related_chunks(documents, metadatas, related_chunks)

            # Fetch procedure chunks if task instruction matches action
            query_action = ActionKindClassifier.determine_action_kind(classification_query)
            is_step_action = query_action and query_intent == QueryIntent.TaskInstruction
            if is_step_action and metadatas:
                procedure_chunks = repository.get_procedure_chunks_by_action(metadatas, query_action, 12)
                chat_engine.append_related_chunks(documents, metadatas, procedure_chunks)

            # Re-order chunks if action matches
            if query_action and documents:
                items = [{"doc": doc, "meta": metadatas[i]} for i, doc in enumerate(documents)]
                def sort_key(item):
                    doc, meta = item["doc"], item["meta"]
                    if ChatEngine.chunk_matches_action(doc, meta, query_action) and ChatEngine.is_procedure_steps(meta):
                        return 0
                    if ChatEngine.chunk_matches_action(doc, meta, query_action):
                        return 1
                    if ChatEngine.chunk_matches_different_action(doc, meta, query_action):
                        return 4
                    return 2
                
                sorted_items = sorted(items, key=sort_key)
                documents = [x["doc"] for x in sorted_items]
                metadatas = [x["meta"] for x in sorted_items]

            # Build context text
            context_text, used_metadatas = chat_engine.build_context_text(documents, metadatas, query_intent)
            chat_engine.remember_lookup_target(effective_message, connection_id)

            # 3. Check simple structured lookups (only in text-only mode)
            if not screenshot_descriptions:
                structured_ans, structured_meta = chat_engine.try_answer_from_structured_context(effective_message, documents, metadatas)
                if structured_ans:
                    citations = CitationHelper.build_full_citations(structured_meta)
                    if not chat_already_started:
                        yield f"event: chat_started\ndata: {{}}\n\n"
                    yield f"event: citations\ndata: {json.dumps(citations)}\n\n"
                    yield f"event: token\ndata: {json.dumps({'text': structured_ans})}\n\n"
                    
                    footer = CitationHelper.build_footer(structured_meta)
                    if footer:
                        yield f"event: token\ndata: {json.dumps({'text': footer})}\n\n"
                    yield "event: chat_ended\ndata: {}\n\n"
                    return

            if not context_text or not context_text.strip():
                if not screenshot_descriptions:
                    if not chat_already_started:
                        yield f"event: chat_started\ndata: {{}}\n\n"
                    yield f"event: citations\ndata: []\n\n"
                    yield f"event: token\ndata: {json.dumps({'text': 'Mình chưa tìm thấy thông tin này trong tài liệu đã nạp.'})}\n\n"
                    yield "event: chat_ended\ndata: {}\n\n"
                    return

            # Build citations response
            citations = CitationHelper.build_full_citations(used_metadatas)
            
            # Yield startup events
            if not chat_already_started:
                yield f"event: chat_started\ndata: {{}}\n\n"
            yield f"event: citations\ndata: {json.dumps(citations)}\n\n"

            # Prepare prompts
            if screenshot_descriptions:
                system_prompt = (
                    "Bạn là trợ lý AI thông minh, hỗ trợ người dùng thao tác trên phần mềm dựa trên ảnh chụp màn hình được cung cấp và tài liệu HDSD (nếu có).\n\n"
                    "Luật trả lời:\n"
                    "1. Được phép mô tả, trả lời các thông tin trực quan dựa trên phần 'ẢNH USER VỪA GỬI'.\n"
                    "2. Đối với hướng dẫn quy trình nghiệp vụ (ví dụ: các bước duyệt, tạo, chỉnh sửa): Chỉ sử dụng thông tin trong phần 'NGỮ CẢNH TÀI LIỆU ĐÃ NẠP'. Không tự ý suy diễn hoặc bịa ra quy trình/thao tác nếu tài liệu không đề cập.\n"
                    "3. Nếu tài liệu đã nạp không có thông tin hoặc quy trình nghiệp vụ tương ứng với màn hình hiển thị trong ảnh, hãy trả lời rõ: \"Tôi không tìm thấy hướng dẫn thao tác cho quy trình này trong tài liệu.\"\n"
                    "4. Trả lời ngắn gọn, trực tiếp bằng tiếng Việt tự nhiên.\n"
                    "5. Không tự thêm nguồn hoặc tham khảo ở cuối câu trả lời."
                )

                user_prompt = "ẢNH USER VỪA GỬI (MÔ TẢ TRỰC QUAN):\n"
                for i, desc in enumerate(screenshot_descriptions, 1):
                    user_prompt += f"Ảnh {i}: {desc}\n"
                user_prompt += "\n"
                user_prompt += f"NGỮ CẢNH TÀI LIỆU ĐÃ NẠP:\n{context_text}\n\n"
                user_prompt += f"Câu hỏi: {effective_message}\n"
            else:
                system_prompt = (
                    "Bạn là trợ lý AI thông minh, chỉ trả lời câu hỏi dựa trên phần NGỮ CẢNH được cung cấp.\n\n"
                    "Luật trả lời:\n"
                    "1. Chỉ sử dụng thông tin trong phần NGỮ CẢNH để trả lời. Không thêm bớt, không tự ý suy diễn, không dùng kiến thức bên ngoài.\n"
                    "2. Nếu ngữ cảnh không có thông tin hoặc không đủ thông tin, bắt buộc phải trả lời đúng: \"Tôi không tìm thấy thông tin này trong tài liệu.\"\n"
                    "3. Đối với câu hỏi yêu cầu các bước thực hiện/hướng dẫn: Chỉ liệt kê các thao tác thật sự theo đúng trình tự từ tài liệu hướng dẫn (ví dụ: Bước 1, Bước 2...). Tuyệt đối không biến nhãn trường, tên cột hoặc các ký tự OCR rác thành các bước thao tác.\n"
                    "4. Bỏ qua các ký tự LaTeX/markup, dòng lặp, hoặc nhãn nhiễu trong ngữ cảnh; không lặp lại cụm từ hoặc dòng quá 2 lần. Dòng có dạng [SLIDE: <title>] là tiêu đề màn hình/tác vụ, dùng để chọn đúng quy trình, tuyệt đối không coi là nhiễu.\n"
                    "5. Trả lời ngắn gọn, trực tiếp, bằng tiếng Việt tự nhiên.\n"
                    "6. Không tự thêm dòng nguồn, tham khảo, hoặc trích dẫn tài liệu ở cuối câu trả lời. Hệ thống sẽ tự thêm."
                )

                user_prompt = (
                    "NGỮ CẢNH TÀI LIỆU ĐÃ NẠP:\n"
                    f"{context_text}\n\n"
                    f"Câu hỏi: {effective_message}\n"
                )

            max_tokens = chat_engine.determine_max_tokens(context_text)

            # Call LLM streaming
            logger.info("Calling vLLM chat completion streaming...")
            response = await chat_engine.openai_client.chat.completions.create(
                model=settings.llm_model_id,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.0,
                max_tokens=max_tokens,
                top_p=1.0,
                frequency_penalty=0.3,
                presence_penalty=0.0,
                stop=["\nNguồn tài liệu:", "\nNguồn:", "\nTham khảo:"],
                stream=True
            )

            generated_answer = []
            async for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    token = chunk.choices[0].delta.content
                    generated_answer.append(token)
                    
                    # Yield token event
                    yield f"event: token\ndata: {json.dumps({'text': token})}\n\n"

                    # Check repetition loop
                    current_text = "".join(generated_answer)
                    if ChatEngine.is_repetition_loop(current_text):
                        logger.warning("Repetition loop detected. Stopping completion stream.")
                        break

            # Build footer citations label
            footer = CitationHelper.build_footer(used_metadatas)
            if footer:
                yield f"event: token\ndata: {json.dumps({'text': footer})}\n\n"

            yield "event: chat_ended\ndata: {}\n\n"

        except Exception as ex:
            logger.error(f"Error in SSE generator stream: {ex}", exc_info=True)
            yield "event: token\ndata: {\"text\": \"\\n[Lỗi kết nối tới mô hình AI hoặc Database]\"}\n\n"
            yield "event: chat_ended\ndata: {}\n\n"

    return StreamingResponse(sse_generator(), media_type="text/event-stream")
