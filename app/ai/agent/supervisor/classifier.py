import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from langchain_core.messages import HumanMessage, SystemMessage
from app.core.config import settings
from app.llmops.factory import get_chat_model
from app.shared.utils.action_classifier import ActionKindClassifier
from app.ai.agent.supervisor.schemas import RouterOutput, IntentType

logger = logging.getLogger(__name__)

GREETING_RESPONSE = (
    "Xin chào! Tôi là trợ lý AI thông minh hỗ trợ tra cứu quy trình, quy chế, chính sách nội bộ "
    "và hướng dẫn thao tác trên hệ thống phần mềm gAMSPro. Tôi có thể giúp gì cho bạn hôm nay?"
)

GRATITUDE_RESPONSE = (
    "Rất vui được hỗ trợ bạn! Nếu bạn cần tra cứu thêm quy trình, chính sách hoặc hướng dẫn thao tác nào khác, "
    "hãy gửi câu hỏi cho tôi nhé."
)

OUT_OF_SCOPE_RESPONSE = (
    "Xin lỗi bạn, tôi là trợ lý AI chuyên trách tra cứu quy trình, quy định nội bộ và hướng dẫn sử dụng "
    "phần mềm gAMSPro. Tôi không có dữ liệu để giải đáp các câu hỏi ngoài phạm vi nghiệp vụ này. "
    "Vui lòng đặt câu hỏi liên quan đến quy chế, biểu mẫu hoặc hướng dẫn hệ thống!"
)

OUT_OF_SCOPE_PATTERNS = [
    r"\b(thời tiết|dự báo thời tiết|nhiệt độ hôm nay)\b",
    r"\b(cách nấu|công thức nấu|món ngon|nấu ăn)\b",
    r"\b(tỷ số bóng đá|kết quả bóng đá|bóng đá ngoại hạng|world cup)\b",
    r"\b(phim hay|rạp chiếu phim|lịch chiếu phim)\b",
    r"\b(kể chuyện cười|hát một bài|làm thơ vui)\b",
    r"\b(xổ số|kết quả xổ số|lô đề|soi cầu)\b",
]

DOMAIN_KEYWORDS = [
    "quy trình", "quy chế", "chính sách", "hướng dẫn", "sổ tay", "hệ thống",
    "gamspro", "tài sản", "mua sắm", "hồ sơ", "phê duyệt", "bàn giao",
    "phiếu yêu cầu", "pyc", "điều chuyển", "thanh lý", "hàng hóa", "hợp đồng",
    "bước", "thao tác", "nhập liệu", "đăng nhập", "mật khẩu", "phân quyền",
    "chức năng", "báo cáo", "kê khai", "chứng từ", "kho", "vật tư", "sửa chữa"
]

@dataclass
class IntentResult:
    intent: str  # "rag", "chitchat", "out_of_scope", "unsafe"
    response: Optional[str] = None
    confidence: float = 1.0
    reasoning: str = ""

class IntentClassifier:
    """
    Supervisor Intent Classifier:
    Phân loại câu hỏi thành các luồng xử lý tối ưu:
    1. 'chitchat': Lời chào, cảm ơn, xã giao -> Trả lời ngay lập tức, không tốn chi phí RAG.
    2. 'out_of_scope': Câu hỏi ngoài phạm vi nghiệp vụ -> Từ chối lịch sự theo mẫu.
    3. 'rag': Câu hỏi nghiệp vụ -> Định tuyến vào Agentic RAG Graph.
    """

    def __init__(self, model_id: Optional[str] = None):
        self.model_id = model_id or getattr(settings, "llm_model_id", "qwen2.5:3b")

    async def classify(
        self,
        query: str,
        history: Optional[List[Dict[str, Any]]] = None,
    ) -> IntentResult:
        clean_query = (query or "").strip()
        if not clean_query:
            return IntentResult(intent="chitchat", response=GREETING_RESPONSE, confidence=1.0, reasoning="empty_query")

        # ── Step 1: Rule-based Fast Path (<1ms) ──
        # 1.1. Lời chào
        if ActionKindClassifier.is_greeting(clean_query):
            logger.info(f"[INTENT] Rule matched: greeting -> chitchat")
            return IntentResult(
                intent="chitchat",
                response=GREETING_RESPONSE,
                confidence=1.0,
                reasoning="rule_greeting",
            )

        # 1.2. Lời cảm ơn
        if ActionKindClassifier.is_gratitude(clean_query):
            logger.info(f"[INTENT] Rule matched: gratitude -> chitchat")
            return IntentResult(
                intent="chitchat",
                response=GRATITUDE_RESPONSE,
                confidence=1.0,
                reasoning="rule_gratitude",
            )

        # 1.3. Lời hỏi danh tính bot / giới thiệu
        BOT_IDENTITY_PATTERNS = [
            r"\b(ban la ai|em la ai|may la ai|who are you)\b",
            r"\b(ban ten gi|em ten gi|ten ban la gi)\b",
            r"\b(ban co the lam gi|em co the lam gi|chuc nang cua ban|chuc nang cua em)\b",
            r"\b(gioi thieu ban than|gioi thieu ve ban)\b",
        ]
        norm = ActionKindClassifier.normalize_text(clean_query)
        for b_pat in BOT_IDENTITY_PATTERNS:
            if re.search(b_pat, norm):
                logger.info(f"[INTENT] Rule matched: bot identity -> chitchat")
                return IntentResult(
                    intent="chitchat",
                    response=GREETING_RESPONSE,
                    confidence=1.0,
                    reasoning="rule_bot_identity",
                )

        # 1.4. Out of scope regex
        for pattern in OUT_OF_SCOPE_PATTERNS:
            if re.search(pattern, clean_query, re.IGNORECASE) or re.search(pattern, norm, re.IGNORECASE):
                logger.info(f"[INTENT] Rule matched: out_of_scope pattern -> {pattern}")
                return IntentResult(
                    intent="out_of_scope",
                    response=OUT_OF_SCOPE_RESPONSE,
                    confidence=0.95,
                    reasoning="rule_out_of_scope",
                )

        # 1.5. Nhận diện RAG rõ ràng qua nghiệp vụ hoặc ActionKind
        if ActionKindClassifier.has_action_intent(clean_query):
            logger.debug(f"[INTENT] Fast path: action intent detected -> rag")
            return IntentResult(intent="rag", confidence=1.0, reasoning="fast_path_action_intent")

        for kw in DOMAIN_KEYWORDS:
            if kw in norm or kw in clean_query.lower():
                logger.debug(f"[INTENT] Fast path: domain keyword '{kw}' detected -> rag")
                return IntentResult(intent="rag", confidence=1.0, reasoning=f"fast_path_keyword_{kw}")

        # Nếu câu hỏi dài hoặc có lịch sử hội thoại, khả năng cao là câu hỏi tiếp nối về nghiệp vụ -> RAG
        if len(clean_query.split()) >= 6 or (history and len(history) > 0):
            return IntentResult(intent="rag", confidence=0.85, reasoning="heuristic_length_or_history")

        # ── Step 2: Lightweight Structured Output LLM Router (cho câu ngắn mơ hồ, timeout 2.0s) ──
        try:
            llm = get_chat_model(model=self.model_id)
            router_prompt = (
                "Bạn là hệ thống điều phối phân loại ý định người dùng (Supervisor Intent Router).\n"
                "Phân loại câu hỏi của người dùng vào đúng 1 trong 3 nhóm:\n"
                "- 'rag': Câu hỏi liên quan công việc, quy trình, quy định, chính sách nội bộ, hướng dẫn hệ thống phần mềm.\n"
                "- 'chitchat': Lời chào hỏi, cảm ơn, khen ngợi, giao tiếp xã giao.\n"
                "- 'out_of_scope': Câu hỏi ngoài phạm vi nghiệp vụ (thời tiết, giải trí, thể thao, nấu ăn, tán gẫu không liên quan).\n"
                "Hãy trả về đúng cấu trúc Pydantic RouterOutput gồm intent, confidence, reasoning và rewritten_query."
            )
            structured_llm = llm.with_structured_output(RouterOutput)
            router_res: RouterOutput = await asyncio.wait_for(
                structured_llm.ainvoke([
                    SystemMessage(content=router_prompt),
                    HumanMessage(content=f"Câu hỏi: {clean_query}")
                ]),
                timeout=2.0,
            )

            intent_val = router_res.intent.value if hasattr(router_res.intent, "value") else str(router_res.intent)
            if intent_val == IntentType.CHITCHAT.value:
                return IntentResult(
                    intent="chitchat",
                    response=GREETING_RESPONSE,
                    confidence=router_res.confidence,
                    reasoning=f"structured_llm: {router_res.reasoning}",
                )
            elif intent_val == IntentType.OUT_OF_SCOPE.value:
                return IntentResult(
                    intent="out_of_scope",
                    response=OUT_OF_SCOPE_RESPONSE,
                    confidence=router_res.confidence,
                    reasoning=f"structured_llm: {router_res.reasoning}",
                )
            else:
                return IntentResult(
                    intent="rag",
                    confidence=router_res.confidence,
                    reasoning=f"structured_llm: {router_res.reasoning}",
                )
        except Exception as ex:
            logger.debug(f"[INTENT] Structured LLM classifier fallback to 'rag': {ex}")
            return IntentResult(intent="rag", confidence=0.7, reasoning="fallback_rag")
