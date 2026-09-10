import logging
from typing import List, Dict
from langchain_core.messages import BaseMessage, SystemMessage
from app.ai.agent.agentic_rag.prompts.registry import get_system_prompt
from app.ai.agent.agentic_rag.state import AgenticRagState
from app.ai.agent.agentic_rag.tools import RAG_TOOLS
from app.llmops.factory import get_chat_model

logger = logging.getLogger(__name__)

async def rag_agent_node(state: AgenticRagState) -> Dict[str, List[BaseMessage]]:
    messages = list(state.get("messages", [])) if isinstance(state, dict) else list(state.messages)

    if not messages or not isinstance(messages[0], SystemMessage):
        system_prompt = get_system_prompt()
        messages = [SystemMessage(content=system_prompt)] + messages

    llm = get_chat_model().bind_tools(RAG_TOOLS)
    response = await llm.ainvoke(messages)

    return {"messages": [response]}

agent_node = rag_agent_node
