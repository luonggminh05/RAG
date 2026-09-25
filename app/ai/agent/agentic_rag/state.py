from typing import Annotated, Any, Optional, List, Dict
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class AgenticRagState(TypedDict):
    """State quản lý ngữ cảnh hội thoại và dữ liệu của Agentic RAG."""
    messages: Annotated[List[BaseMessage], add_messages]
    user_query: str
    session_id: str
    user_roles: Optional[str]
    user_department: Optional[str]
    documents: List[str]
    citations: List[Dict[str, Any]]
    is_relevant: bool
    final_answer: str
    chat_history: Optional[List[Dict[str, Any]]]
    vision_context: Optional[str]
    selected_model: Optional[str]
    top_k: Optional[int]

