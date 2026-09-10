import base64
import json
import logging
import asyncio
import re
import uuid
from typing import AsyncGenerator, List, Optional, Dict, Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.config import settings
from app.modules.chat.repository import ChatRepository
from app.ai.rag.retrieval.retriever import VectorRetriever
from app.ai.vision.vision_service import VisionService
from app.ai.guardrails.guardrail import InputGuardrail, OutputGuardrail, SAFE_FALLBACK_MESSAGE
from app.ai.rag.citation.helper import CitationHelper
from app.modules.chat.api.v1.schemas import ChatImageInput
from app.ai.agent.supervisor.classifier import IntentClassifier
from app.ai.agent.agentic_rag.graph.graph import rag_graph
from app.ai.agent.agentic_rag.tools.search_policy_docs_tool import set_rbac_context
from app.llmops.langfuse import get_langfuse_langchain_config
from app.llmops.factory import get_chat_model

logger = logging.getLogger(__name__)


class ChatService:
    def __init__(
        self,
        repository: ChatRepository,
        retriever: VectorRetriever,
        vision_service: VisionService,
        intent_classifier: Optional[IntentClassifier] = None,
    ):
        self.repository = repository
        self.retriever = retriever
        self.vision_service = vision_service
        self.intent_classifier = intent_classifier or IntentClassifier()

    async def _generate_title(self, conversation_id: int, base_query: str) -> None:
        """Tự động tạo tiêu đề ngắn gọn cho cuộc trò chuyện qua LLM chạy ngầm."""
        fallback_title = re.sub(r'\s+', ' ', base_query)[:50].strip() or "Cuộc hội thoại mới"
        try:
            model_id = getattr(settings, "llm_model_id", "qwen2.5:3b")
            llm = get_chat_model(model=model_id)
            messages = [
                SystemMessage(
                    content="Bạn là chuyên viên đặt tiêu đề hội thoại. Hãy tạo một tiêu đề tiếng Việt ngắn gọn (từ 3 đến 7 từ), không để dấu ngoặc kép, không chứa định dạng markdown, phản ánh đúng nội dung câu hỏi sau:"
                ),
                HumanMessage(content=base_query[:200]),
            ]
            response = await asyncio.wait_for(
                llm.ainvoke(messages),
                timeout=5.0,
            )
            title = (response.content if hasattr(response, "content") else str(response)).strip().strip("\"'").replace("\n", " ")
            if title and len(title) > 2:
                self.repository.update_conversation_title(conversation_id, title[:80])
            else:
                self.repository.update_conversation_title(conversation_id, fallback_title)
        except Exception as ex:
            logger.debug(f"[CHAT] Auto-generate title for conv={conversation_id} skipped: {ex}")
            self.repository.update_conversation_title(conversation_id, fallback_title)

    @staticmethod
    async def _stream_text_adaptive(text: str) -> AsyncGenerator[str, None]:
        """Phát token từng từ mượt mà (natural pacing) thay vì nguyên cụm."""
        tokens = re.findall(r"\S+\s*|\s+", text)
        for token in tokens:
            yield f"event: token\ndata: {json.dumps({'text': token}, ensure_ascii=False)}\n\n"
            delay = 0.04 if any(p in token for p in ".!?,;:\n") else (0.015 if len(token) > 4 else 0.008)
            await asyncio.sleep(delay)

    async def stream_chat(
        self,
        message: str,
        images: Optional[List[ChatImageInput]] = None,
        user_roles: Optional[str] = None,
        user_department: Optional[str] = None,
        conversation_id: Optional[str] = None,
        user_id: Optional[str] = None,
        model: Optional[str] = None,
        enable_vision: bool = True,
        top_k: Optional[int] = None,
        is_retry: bool = False,
        retry_message_id: Optional[int] = None,
        is_edit: bool = False,
        edit_message_id: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Luồng SSE Stream xử lý phản hồi RAG tích hợp Fast Pipeline:
        - Supervisor Intent Router (RAG vs Chitchat vs Out-of-Scope)
        - Langfuse Tracing Context & Observability
        - Query Contextualization & Multi-turn Conversation
        - Vision Analysis (Multimodal Screenshots)
        - Dynamic Top-K Query Analysis & Cross-Encoder Reranker
        - Edit Message & Retry Branching support
        - Token-level streaming & Natural pacing
        """
        identifier = user_id or (str(conversation_id) if conversation_id else None) or "anonymous"
        try:
            async for sse_event in self._stream_chat_internal(
                message=message,
                images=images,
                user_roles=user_roles,
                user_department=user_department,
                conversation_id=conversation_id,
                user_id=user_id,
                model=model,
                enable_vision=enable_vision,
                top_k=top_k,
                is_retry=is_retry,
                retry_message_id=retry_message_id,
                is_edit=is_edit,
                edit_message_id=edit_message_id,
            ):
                yield sse_event
        finally:
            if getattr(settings, "rate_limit_enabled", False):
                try:
                    from app.security.rate_limiter import get_rate_limiter
                    await get_rate_limiter().release(identifier)
                except Exception as rel_err:
                    logger.debug(f"[CHAT] Rate limiter release error: {rel_err}")

    async def _stream_chat_internal(
        self,
        message: str,
        images: Optional[List[ChatImageInput]] = None,
        user_roles: Optional[str] = None,
        user_department: Optional[str] = None,
        conversation_id: Optional[str] = None,
        user_id: Optional[str] = None,
        model: Optional[str] = None,
        enable_vision: bool = True,
        top_k: Optional[int] = None,
        is_retry: bool = False,
        retry_message_id: Optional[int] = None,
        is_edit: bool = False,
        edit_message_id: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        # 1. Resolve or Create Conversation in DB
        conv_id_int: Optional[int] = None
        if conversation_id and str(conversation_id).isdigit():
            conv_id_int = int(conversation_id)
            conv = self.repository.get_conversation(conv_id_int)
            if not conv:
                conv_id_int = self.repository.create_conversation(user_id=user_id, title="Cuộc hội thoại mới")
        else:
            conv_id_int = self.repository.create_conversation(user_id=user_id, title="Cuộc hội thoại mới")

        base_query = (message or "").strip()
        screenshot_descriptions: List[str] = []
        selected_model = model or getattr(settings, "llm_model_id", "qwen2.5vl:7b")

        # 2. Xử lý ảnh đính kèm (nếu bật chế độ Vision)
        has_images = images and len(images) > 0
        if has_images:
            if not enable_vision:
                yield "event: chat_started\ndata: {}\n\n"
                warning_msg = "*Chế độ đọc ảnh (Vision Mode) đang tắt. Bỏ qua phân tích ảnh đính kèm.*\\n\\n"
                yield f"event: token\ndata: {json.dumps({'text': warning_msg}, ensure_ascii=False)}\n\n"
            else:
                if len(images) > 3:
                    yield "event: chat_started\ndata: {}\n\n"
                    yield "event: token\ndata: {\"text\": \"\\n[Lỗi: Chỉ gửi tối đa 3 ảnh cùng lúc]\"}\n\n"
                    yield "event: chat_ended\ndata: {}\n\n"
                    return

                total_bytes = 0
                decoded_images = []
                for img in images:
                    if not img.base64:
                        continue
                    try:
                        b64_data = img.base64.split(",")[1] if "," in img.base64 else img.base64
                        raw_bytes = base64.b64decode(b64_data)
                        total_bytes += len(raw_bytes)
                        if total_bytes > 5 * 1024 * 1024:
                            yield "event: chat_started\ndata: {}\n\n"
                            yield "event: token\ndata: {\"text\": \"\\n[Lỗi: Tổng dung lượng ảnh vượt quá 5MB]\"}\n\n"
                            yield "event: chat_ended\ndata: {}\n\n"
                            return
                        decoded_images.append(raw_bytes)
                    except Exception:
                        yield "event: chat_started\ndata: {}\n\n"
                        yield "event: token\ndata: {\"text\": \"\\n[Lỗi: Giải mã hình ảnh base64 thất bại]\"}\n\n"
                        yield "event: chat_ended\ndata: {}\n\n"
                        return

                if decoded_images:
                    yield "event: chat_started\ndata: {}\n\n"
                    yield "event: thinking\ndata: {\"text\": \"Đang phân tích hình ảnh đính kèm bằng Vision Service...\\n\"}\n\n"
                    tasks = [self.vision_service.describe_screenshot(img_b, base_query) for img_b in decoded_images]
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    for desc in results:
                        if isinstance(desc, str) and desc.strip():
                            screenshot_descriptions.append(desc.strip())

        if not base_query and screenshot_descriptions:
            base_query = screenshot_descriptions[0]

        if not base_query:
            yield "event: chat_started\ndata: {}\n\n"
            yield "event: token\ndata: {\"text\": \"Bạn chưa nhập câu hỏi và không có hình ảnh hợp lệ để phân tích.\"}\n\n"
            yield "event: chat_ended\ndata: {}\n\n"
            return

        # 3. Input Guardrail
        guard_res = InputGuardrail.validate(base_query)
        if not guard_res.is_safe:
            yield "event: chat_started\ndata: {}\n\n"
            yield f"event: token\ndata: {json.dumps({'text': guard_res.fallback_message or SAFE_FALLBACK_MESSAGE}, ensure_ascii=False)}\n\n"
            yield "event: chat_ended\ndata: {}\n\n"
            return

        # 4. Save User Message & Conversation History Handling (with Edit & Retry Support)
        prior_history: List[Dict[str, Any]] = []
        try:
            if is_edit and edit_message_id is not None:
                self.repository.update_message_content(edit_message_id, message or "[Hình ảnh]")
                self.repository.truncate_messages_after(conv_id_int, edit_message_id)
                all_prior = self.repository.get_messages_up_to(conv_id_int, edit_message_id, limit=6)
                prior_history = [m for m in all_prior if m.get("id") != edit_message_id]
                logger.info(f"[CHAT] Handled edit for message_id={edit_message_id}, conv={conv_id_int}")
            elif is_retry and retry_message_id is not None:
                # Xóa các tin nhắn sau mốc retry_message_id
                self.repository.truncate_messages_after(conv_id_int, retry_message_id)
                all_prior = self.repository.get_messages_up_to(conv_id_int, retry_message_id, limit=6)
                prior_history = [m for m in all_prior if m.get("id") != retry_message_id]
                logger.info(f"[CHAT] Handled retry for message_id={retry_message_id}, conv={conv_id_int}")
            else:
                self.repository.add_message(conv_id_int, "user", message or "[Hình ảnh]")
                msg_count = self.repository.count_messages(conv_id_int)
                if msg_count <= 1:
                    asyncio.create_task(self._generate_title(conv_id_int, base_query))
                all_msgs = self.repository.get_messages(conv_id_int, limit=8)
                # Bỏ tin nhắn user vừa thêm ra khỏi prior_history để tránh lặp
                prior_history = all_msgs[:-1] if all_msgs else []
        except Exception as ex:
            logger.warning(f"[CHAT] Message history operation warning: {ex}")

        # 5. Supervisor Intent Router (P2.1)
        intent_res = await self.intent_classifier.classify(base_query, history=prior_history)

        if intent_res.intent in ("chitchat", "out_of_scope"):
            if not has_images:
                yield "event: chat_started\ndata: {}\n\n"
            ans_text = intent_res.response or "Xin chào! Tôi có thể hỗ trợ gì cho bạn?"
            async for sse_event in self._stream_text_adaptive(ans_text):
                yield sse_event
            yield "event: chat_ended\ndata: {}\n\n"
            try:
                self.repository.add_message(conv_id_int, "assistant", ans_text, trace_id=str(uuid.uuid4()))
                self.repository.touch_conversation(conv_id_int)
            except Exception:
                pass
            return

        # 6. Chuẩn bị ngữ cảnh cho Agentic RAG Graph
        if not has_images:
            yield "event: chat_started\ndata: {}\n\n"

        vision_ctx = "\n".join(screenshot_descriptions) if screenshot_descriptions else None

        # Thiết lập ngữ cảnh RBAC và Chat History cho tool retrieval
        set_rbac_context(
            user_roles=user_roles,
            user_department=user_department,
            chat_history=prior_history,
        )

        # Cấu hình Langfuse Tracing
        trace_id = str(uuid.uuid4())
        langfuse_config = get_langfuse_langchain_config(
            session_id=str(conv_id_int),
            user_id=str(user_id),
            tags=["rag-service", "agentic-rag"],
            metadata={
                "conversation_id": conv_id_int,
                "user_roles": user_roles,
                "user_department": user_department,
                "model": selected_model,
                "is_retry": is_retry,
                "trace_id": trace_id,
            },
            trace_name="AgenticRAG_ChatStream",
        )

        initial_state = {
            "messages": [HumanMessage(content=base_query)],
            "user_query": base_query,
            "session_id": str(conv_id_int),
            "user_roles": user_roles,
            "user_department": user_department,
            "documents": [],
            "citations": [],
            "is_relevant": False,
            "retry_count": 0,
            "final_answer": "",
            "chat_history": prior_history,
            "vision_context": vision_ctx,
            "selected_model": selected_model,
            "rewritten_query": None,
            "top_k": top_k,
        }

        # 7. Hàng đợi bất đồng bộ & Worker xử lý Graph
        queue: asyncio.Queue = asyncio.Queue()

        async def _run_agentic_graph():
            collected_tokens: List[str] = []
            in_thinking = False
            current_active_node = ""
            final_citations: List[Dict[str, Any]] = []
            final_answer_text = ""

            try:
                async for event in rag_graph.astream_events(
                    initial_state,
                    version="v2",
                    config=langfuse_config,
                ):
                    event_type = event.get("event")
                    node_name = event.get("metadata", {}).get("langgraph_node", "") or event.get("name", "")

                    # 7.1. Cập nhật node & trạng thái suy nghĩ
                    if event_type == "on_chain_start":
                        name = event.get("name", "")
                        if name == "retrieve_rag_node":
                            current_active_node = "retrieve_rag_node"
                            await queue.put(("thinking", "Đang tra cứu và truy xuất tài liệu quy chế, chính sách liên quan...\n"))
                        elif name == "generator_node":
                            current_active_node = "generator_node"
                            await queue.put(("thinking", "Đang tổng hợp thông tin và định dạng câu trả lời...\n"))

                    # 7.2. Bắt Token Streaming từ Chat Model trong Generator Node
                    elif event_type == "on_chat_model_stream":
                        chunk = event.get("data", {}).get("chunk")
                        if not chunk:
                            continue

                        # Chỉ stream token của câu trả lời người dùng, bỏ qua raw JSON tool-calls
                        if hasattr(chunk, "tool_call_chunks") and chunk.tool_call_chunks:
                            continue

                        token_content = chunk.content if hasattr(chunk, "content") else str(chunk)
                        if isinstance(token_content, list):
                            token_content = "".join(
                                item.get("text", "") if isinstance(item, dict) else str(item)
                                for item in token_content
                            )
                        if not token_content:
                            continue

                        # Xử lý thẻ suy luận <think>...</think> (DeepSeek-R1 CoT)
                        if "<think>" in token_content:
                            in_thinking = True
                            parts = token_content.split("<think>")
                            if parts[0]:
                                collected_tokens.append(parts[0])
                                await queue.put(("token", parts[0]))
                            if len(parts) > 1 and parts[1]:
                                if "</think>" in parts[1]:
                                    t_parts = parts[1].split("</think>")
                                    await queue.put(("thinking", t_parts[0]))
                                    in_thinking = False
                                    if t_parts[1]:
                                        collected_tokens.append(t_parts[1])
                                        await queue.put(("token", t_parts[1]))
                                else:
                                    await queue.put(("thinking", parts[1]))
                        elif in_thinking:
                            if "</think>" in token_content:
                                parts = token_content.split("</think>")
                                if parts[0]:
                                    await queue.put(("thinking", parts[0]))
                                in_thinking = False
                                if len(parts) > 1 and parts[1]:
                                    collected_tokens.append(parts[1])
                                    await queue.put(("token", parts[1]))
                            else:
                                await queue.put(("thinking", token_content))
                        else:
                            collected_tokens.append(token_content)
                            await queue.put(("token", token_content))

                    # 7.3. Bắt kết quả node kết thúc
                    elif event_type == "on_chain_end":
                        data_output = event.get("data", {}).get("output")
                        if isinstance(data_output, dict):
                            if "citations" in data_output and data_output["citations"]:
                                final_citations = data_output["citations"]
                            if "final_answer" in data_output and data_output["final_answer"]:
                                final_answer_text = str(data_output["final_answer"])

                # Hoàn tất graph run
                raw_answer = "".join(collected_tokens).strip() or final_answer_text
                sanitized_out = OutputGuardrail.sanitize(raw_answer)
                clean_answer = sanitized_out.sanitized_text if sanitized_out.is_safe else SAFE_FALLBACK_MESSAGE

                footer = CitationHelper.build_footer(final_citations) if final_citations else ""
                full_saved_message = clean_answer + (f"\n\n{footer}" if footer else "")

                # Lưu tin nhắn trợ lý vào DB kèm trace_id
                self.repository.add_message(conv_id_int, "assistant", full_saved_message, trace_id=trace_id)
                self.repository.touch_conversation(conv_id_int)

                await queue.put(("citations", (final_citations, footer)))
                await queue.put(("done", None))

            except Exception as ex:
                logger.error(f"[CHAT] Agentic RAG Graph execution error: {ex}", exc_info=True)
                await queue.put(("error", str(ex)))

        # Khởi chạy background worker
        worker_task = asyncio.create_task(_run_agentic_graph())  # noqa: F841

        # 8. Tiêu thụ Queue và phát các sự kiện SSE
        saved_citations: List[Dict[str, Any]] = []
        saved_footer: str = ""

        try:
            while True:
                item = await queue.get()
                item_type, item_data = item[0], item[1]

                if item_type == "token":
                    yield f"event: token\ndata: {json.dumps({'text': item_data}, ensure_ascii=False)}\n\n"
                elif item_type == "thinking":
                    yield f"event: thinking\ndata: {json.dumps({'text': item_data}, ensure_ascii=False)}\n\n"
                elif item_type == "citations":
                    saved_citations, saved_footer = item_data
                elif item_type == "done":
                    break
                elif item_type == "error":
                    err_display = f"\n[Lỗi xử lý từ hệ thống AI '{selected_model}': {item_data}]"
                    yield f"event: token\ndata: {json.dumps({'text': err_display}, ensure_ascii=False)}\n\n"
                    break
        except asyncio.CancelledError:
            logger.info(f"[CHAT] Client disconnected from stream conv={conv_id_int}. Background graph worker continues.")
            raise

        # 9. Gửi footer & Citations Event
        if saved_footer:
            yield f"event: token\ndata: {json.dumps({'text': saved_footer}, ensure_ascii=False)}\n\n"

        if saved_citations:
            yield f"event: citations\ndata: {json.dumps({'citations': saved_citations, 'footer': saved_footer}, ensure_ascii=False)}\n\n"

        yield "event: chat_ended\ndata: {}\n\n"
