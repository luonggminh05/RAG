from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from app.ai.agent.agentic_rag.nodes.agent_node import rag_agent_node
from app.ai.agent.agentic_rag.nodes.generator_node import generator_node
from app.ai.agent.agentic_rag.nodes.grader_node import grader_node
from app.ai.agent.agentic_rag.state import AgenticRagState
from app.ai.agent.agentic_rag.tools import RAG_TOOLS

MAX_RETRIES = 2

def should_retrieve_or_answer(state: AgenticRagState) -> str:
    messages = state.get("messages", []) if isinstance(state, dict) else getattr(state, "messages", [])
    if not messages:
        return "generator_node"
    last_message = messages[-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools_node"
    return "generator_node"

def should_generate_or_retry(state: AgenticRagState) -> str:
    is_relevant = state.get("is_relevant", False) if isinstance(state, dict) else getattr(state, "is_relevant", False)
    retry_count = state.get("retry_count", 0) if isinstance(state, dict) else getattr(state, "retry_count", 0)

    if is_relevant or retry_count >= MAX_RETRIES:
        return "generator_node"
    return "rag_agent_node"

graph = StateGraph(AgenticRagState)

graph.add_node("rag_agent_node", rag_agent_node)
graph.add_node("tools_node", ToolNode(RAG_TOOLS))
graph.add_node("grader_node", grader_node)
graph.add_node("generator_node", generator_node)

graph.set_entry_point("rag_agent_node")

graph.add_conditional_edges(
    "rag_agent_node",
    should_retrieve_or_answer,
    {
        "tools_node": "tools_node",
        "generator_node": "generator_node",
    },
)

graph.add_edge("tools_node", "grader_node")

graph.add_conditional_edges(
    "grader_node",
    should_generate_or_retry,
    {
        "generator_node": "generator_node",
        "rag_agent_node": "rag_agent_node",
    },
)

graph.add_edge("generator_node", END)

rag_graph = graph.compile()
