"""
LangGraph Workflow cho RAG Fast Pipeline (app/ai/agent/agentic_rag/graph/graph.py).
Quy trình tối giản 2 bước:
1. retrieve_rag_node: Truy xuất song song Hybrid Search (Vector + Fulltext RRF) & Reranker.
2. generator_node: Tổng hợp câu trả lời có trích dẫn nguồn chuẩn xác, hỗ trợ Token Streaming.
"""

from langgraph.graph import END, StateGraph

from app.ai.agent.agentic_rag.nodes.generator_node import generator_node
from app.ai.agent.agentic_rag.nodes.retrieve_node import retrieve_rag_node
from app.ai.agent.agentic_rag.state import AgenticRagState


# Khởi tạo Graph
graph = StateGraph(AgenticRagState)

# Đăng ký các Nodes
graph.add_node("retrieve_rag_node", retrieve_rag_node)
graph.add_node("generator_node", generator_node)

# Thiết lập điểm vào và các cạnh
graph.set_entry_point("retrieve_rag_node")
graph.add_edge("retrieve_rag_node", "generator_node")
graph.add_edge("generator_node", END)

# Biên dịch Graph
rag_graph = graph.compile()
