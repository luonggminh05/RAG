import logging
from typing import Any, Dict, List
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from app.ai.agent.agentic_rag.prompts.registry import get_generator_prompt
from app.ai.agent.agentic_rag.state import AgenticRagState
from app.llmops.factory import get_chat_model

logger = logging.getLogger(__name__)

async def generator_node(state: AgenticRagState) -> Dict[str, Any]:
    documents = state.get("documents", []) if isinstance(state, dict) else getattr(state, "documents", [])
    citations = state.get("citations", []) if isinstance(state, dict) else getattr(state, "citations", [])
    is_relevant = state.get("is_relevant", False) if isinstance(state, dict) else getattr(state, "is_relevant", False)
    user_query = state.get("user_query", "") if isinstance(state, dict) else getattr(state, "user_query", "")
    messages = state.get("messages", []) if isinstance(state, dict) else getattr(state, "messages", [])
    chat_history = state.get("chat_history", []) if isinstance(state, dict) else getattr(state, "chat_history", [])
    vision_context = state.get("vision_context", None) if isinstance(state, dict) else getattr(state, "vision_context", None)
    selected_model = state.get("selected_model", None) if isinstance(state, dict) else getattr(state, "selected_model", None)

    # 1. Trực tiếp / chitchat
    if not documents and not citations:
        if messages:
            last_msg = messages[-1]
            if isinstance(last_msg, AIMessage) and not getattr(last_msg, "tool_calls", None):
                return {"final_answer": str(last_msg.content)}

    # 2. Không tìm thấy tài liệu phù hợp
    if not documents or not is_relevant:
        answer = "Tôi không tìm thấy thông tin phù hợp trong tài liệu được cấp quyền truy cập."
        return {"final_answer": answer, "messages": [AIMessage(content=answer)]}

    # 3. Tổng hợp câu trả lời
    context_parts: List[str] = []
    for i, doc in enumerate(documents, 1):
        cit = citations[i - 1] if i - 1 < len(citations) else {}
        source = cit.get("source") or cit.get("file_name") or "Tài liệu" if isinstance(cit, dict) else "Tài liệu"
        page = cit.get("page") or cit.get("slide") or "" if isinstance(cit, dict) else ""
        page_info = f", Trang {page}" if page else ""
        citation_label = f"[Nguồn {i}: {source}{page_info}]"
        context_parts.append(f"{citation_label}\n{doc}")

    context_str = "\n\n---\n\n".join(context_parts)
    llm_kwargs = {}
    if selected_model:
        llm_kwargs["model"] = selected_model
    llm = get_chat_model(**llm_kwargs)
    generator_prompt = get_generator_prompt()

    augmented_user_query = user_query
    if vision_context and vision_context.strip():
        augmented_user_query = f"{user_query}\n\n[Mô tả ảnh chụp màn hình]:\n{vision_context.strip()}"

    llm_messages: List[Any] = [SystemMessage(content=generator_prompt)]

    # Thêm lịch sử hội thoại nhiều lượt (nếu có)
    if chat_history:
        for turn in chat_history[-6:]:  # Lấy tối đa 6 lượt hội thoại gần nhất
            role = turn.get("role")
            content = turn.get("content", "")
            if role == "user" and content:
                llm_messages.append(HumanMessage(content=content))
            elif role == "assistant" and content:
                llm_messages.append(AIMessage(content=content))

    llm_messages.append(
        HumanMessage(content=f"Câu hỏi của người dùng: {augmented_user_query}\n\nNGỮ CẢNH TÀI LIỆU:\n{context_str}")
    )

    response = await llm.ainvoke(llm_messages)
    answer = response.content if hasattr(response, "content") else str(response)
    return {"final_answer": answer, "messages": [AIMessage(content=answer)]}
