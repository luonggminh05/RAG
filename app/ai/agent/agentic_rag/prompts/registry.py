from pathlib import Path

_DIR = Path(__file__).parent / "v1"

def get_system_prompt() -> str:
    p = _DIR / "system.md"
    return p.read_text(encoding="utf-8") if p.exists() else "Bạn là Trợ lý AI hỗ trợ tra cứu tài liệu."

def get_grader_prompt() -> str:
    p = _DIR / "grader.md"
    return p.read_text(encoding="utf-8") if p.exists() else "Đánh giá xem tài liệu có liên quan tới câu hỏi không."

def get_generator_prompt() -> str:
    p = _DIR / "generator.md"
    return p.read_text(encoding="utf-8") if p.exists() else "Tổng hợp câu trả lời từ tài liệu."
