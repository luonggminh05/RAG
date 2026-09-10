from pydantic import BaseModel, Field

class DocumentGradeOutput(BaseModel):
    """Output có cấu trúc của Document Grader Node."""
    is_relevant: bool = Field(
        description="True nếu tài liệu chứa thông tin liên quan hoặc hữu ích cho câu hỏi; False nếu hoàn toàn không liên quan."
    )
    reasoning: str = Field(
        default="",
        description="Lý do ngắn gọn cho việc đánh giá liên quan hay không."
    )
