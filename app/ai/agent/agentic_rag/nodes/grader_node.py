import json
import logging
from typing import Any, Dict, List
from langchain_core.messages import HumanMessage, SystemMessage
from app.ai.agent.agentic_rag.nodes.schemas import DocumentGradeOutput
from app.ai.agent.agentic_rag.prompts.registry import get_grader_prompt
from app.ai.agent.agentic_rag.state import AgenticRagState
from app.llmops.factory import get_chat_model

logger = logging.getLogger(__name__)

async def grader_node(state: AgenticRagState) -> Dict[str, Any]:
    messages = state.get("messages", []) if isinstance(state, dict) else getattr(state, "messages", [])
    retry_count = state.get("retry_count", 0) if isinstance(state, dict) else getattr(state, "retry_count", 0)

    tool_content = ""
    for msg in reversed(messages):
        if getattr(msg, "type", "") == "tool" or hasattr(msg, "tool_call_id"):
            tool_content = str(msg.content)
            break
        elif isinstance(msg, dict) and (msg.get("role") == "tool" or msg.get("type") == "tool"):
            tool_content = str(msg.get("content", ""))
            break

    if not tool_content and messages:
        last_msg = messages[-1]
        tool_content = last_msg.content if hasattr(last_msg, "content") else str(last_msg.get("content", "")) if isinstance(last_msg, dict) else ""

    documents: List[str] = []
    citations: List[Dict[str, Any]] = []

    try:
        if tool_content:
            payload = json.loads(tool_content)
            if isinstance(payload, dict):
                documents = payload.get("documents", [])
                citations = payload.get("citations", [])
    except Exception as ex:
        logger.warning(f"[GRADER] Failed to parse tool response: {ex}")

    if not documents:
        return {
            "documents": [],
            "citations": [],
            "is_relevant": False,
            "retry_count": retry_count + 1,
        }

    user_query = state.get("user_query", "") if isinstance(state, dict) else getattr(state, "user_query", "")
    if not user_query and messages:
        for msg in messages:
            if getattr(msg, "type", "") in ("human", "user") or (isinstance(msg, dict) and msg.get("role") in ("human", "user")):
                user_query = msg.content if hasattr(msg, "content") else str(msg.get("content", ""))
                break

    context_preview = "\n---\n".join(str(d) for d in documents[:3])

    try:
        llm = get_chat_model().with_structured_output(DocumentGradeOutput)
        grader_prompt = get_grader_prompt()
        result: DocumentGradeOutput = await llm.ainvoke(
            [
                SystemMessage(content=grader_prompt),
                HumanMessage(
                    content=f"Câu hỏi của người dùng: {user_query}\n\nCác đoạn tài liệu thu được:\n{context_preview}"
                ),
            ]
        )
        is_relevant = bool(result.is_relevant)
        logger.info(f"[GRADER] Document Grader result: is_relevant={is_relevant}, reasoning={result.reasoning}")
    except Exception as e:
        logger.warning(f"[GRADER] Error executing grader LLM, fallback is_relevant=True: {e}")
        is_relevant = True

    update: Dict[str, Any] = {
        "documents": documents,
        "citations": citations,
        "is_relevant": is_relevant,
    }
    if not is_relevant:
        update["retry_count"] = retry_count + 1

    return update
