import logging
import re
from dataclasses import dataclass
from typing import Optional, List, Tuple

logger = logging.getLogger(__name__)

SAFE_FALLBACK_MESSAGE = (
    "Xin lỗi, tôi là trợ lý AI chuyên trách của hệ thống. "
    "Tôi chỉ có thể hỗ trợ các thông tin liên quan đến tài liệu, quy trình và hướng dẫn thao tác đã nạp. "
    "Vui lòng đặt câu hỏi phù hợp với phạm vi hỗ trợ."
)

_JAILBREAK_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"ignore\s+(all\s+)?(previous|prior|system)\s+instructions?", re.IGNORECASE), "prompt_injection_ignore_instructions"),
    (re.compile(r"bỏ\s+qua\s+(toàn\s+bộ\s+|hết\s+)?(hướng\s+dẫn|chỉ\s+dẫn|quy\s+tắc|câu\s+lệnh)\s+(trước|cũ|ban\s+đầu)", re.IGNORECASE), "prompt_injection_ignore_instructions_vi"),
    (re.compile(r"quên\s+(hết|toàn\s+bộ)\s+(các\s+)?(hướng\s+dẫn|quy\s+tắc|lệnh)\s+(trước|cũ)", re.IGNORECASE), "prompt_injection_forget_instructions_vi"),
    (re.compile(r"(reveal|print|show|dump|output)\s+(your\s+|the\s+)?(system\s+prompt|initial\s+instructions?|hidden\s+prompt)", re.IGNORECASE), "system_prompt_leakage_en"),
    (re.compile(r"(tiết\s+lộ|in\s+ra|hiển\s+thị|cho\s+tôi\s+xem)\s+(system\s+prompt|lệnh\s+hệ\s+thống|hướng\s+dẫn\s+ban\s+đầu|prompt\s+ẩn)", re.IGNORECASE), "system_prompt_leakage_vi"),
    (re.compile(r"(dan\s+mode|developer\s+mode|unrestricted\s+ai|jailbreak)", re.IGNORECASE), "jailbreak_dan_mode"),
    (re.compile(r"từ\s+giờ\s+bạn\s+là\s+(một\s+ai\s+không\s+giới\s+hạn|hacker|nhân\s+vật\s+phản\s+diện)", re.IGNORECASE), "jailbreak_persona_vi"),
    (re.compile(r"(UNION\s+SELECT|DROP\s+TABLE|DELETE\s+FROM|INSERT\s+INTO|1=1\s*--|OR\s+'1'='1')", re.IGNORECASE), "sqli_attempt"),
    (re.compile(r"(cách\s+tấn\s+công|hack\s+vào|xâm\s+nhập|phá\s+hoại)\s+(hệ\s+thống|máy\s+chủ|server|database)", re.IGNORECASE), "malicious_infrastructure_attack"),
]

_SENSITIVE_OUTPUT_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"(sk-[a-zA-Z0-9_-]{20,})"), "openai_api_key"),
    (re.compile(r"(AIzaSy[a-zA-Z0-9_-]{33})"), "google_gemini_api_key"),
    (re.compile(r"(sk-ant-[a-zA-Z0-9_-]{20,})"), "anthropic_api_key"),
    (re.compile(r"(hf_[a-zA-Z0-9]{30,})"), "huggingface_token"),
    (re.compile(r"-----BEGIN\s+(RSA\s+|OPENSSH\s+|EC\s+)?PRIVATE\s+KEY-----"), "private_key_leak"),
    (re.compile(r"(Server|Data Source|Host|Database|Initial Catalog)\s*=\s*[^;]+;.*?(Password|Pwd)\s*=\s*[^;\s]+", re.IGNORECASE | re.DOTALL), "db_connection_string_leak"),
    (re.compile(r"(mongodb(\+srv)?|postgresql|postgres|mysql|redis)://[^\s:]+:[^\s@]+@[^\s/]+", re.IGNORECASE), "db_uri_leak"),
    (re.compile(r"(password|mật\s+khẩu|mat_khau|pwd)\s*[:=]\s*['\"]?[^\s'\";]{4,}['\"]?", re.IGNORECASE), "plaintext_password_leak"),
]

@dataclass
class GuardrailResult:
    is_safe: bool
    violation_type: Optional[str] = None
    fallback_message: Optional[str] = None
    sanitized_text: Optional[str] = None


class InputGuardrail:
    @classmethod
    def validate(cls, query: str) -> GuardrailResult:
        if not query or not query.strip():
            return GuardrailResult(is_safe=True)

        normalized_query = query.strip()
        for pattern, violation_type in _JAILBREAK_PATTERNS:
            if pattern.search(normalized_query):
                logger.warning(f"[INPUT GUARDRAIL BLOCKED] Vi phạm '{violation_type}' trong câu hỏi: '{query[:100]}'")
                return GuardrailResult(
                    is_safe=False,
                    violation_type=violation_type,
                    fallback_message=SAFE_FALLBACK_MESSAGE,
                )

        return GuardrailResult(is_safe=True)


class OutputGuardrail:
    @classmethod
    def sanitize(cls, response_text: str) -> GuardrailResult:
        if not response_text or not response_text.strip():
            return GuardrailResult(is_safe=True, sanitized_text=response_text)

        for pattern, violation_type in _SENSITIVE_OUTPUT_PATTERNS:
            if pattern.search(response_text):
                logger.error(f"[OUTPUT GUARDRAIL BLOCKED] Phát hiện rò rỉ '{violation_type}' trong phản hồi LLM!")
                return GuardrailResult(
                    is_safe=False,
                    violation_type=violation_type,
                    fallback_message=SAFE_FALLBACK_MESSAGE,
                    sanitized_text=SAFE_FALLBACK_MESSAGE,
                )

        return GuardrailResult(is_safe=True, sanitized_text=response_text)
