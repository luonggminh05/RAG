"""
Factory function khởi tạo Reranker theo tham số cấu hình RERANKER_TYPE trong .env.
"""

from app.ai.rag.reranker.base import BaseReranker
from app.ai.rag.reranker.disabled import DisabledReranker
from app.core.config import settings


def get_reranker(
    reranker_type: str | None = None,
    model_name: str | None = None,
) -> BaseReranker:
    """
    Factory tạo Reranker instance theo cấu hình hoặc tham số truyền vào.
    - 'bge' / 'cross_encoder' / 'sentence_transformers': CrossEncoderReranker (BAAI/bge-reranker-base)
    - 'flashrank': FlashRank Reranker
    - 'disabled': Passthrough (giữ nguyên thứ tự RRF, mặc định)
    """
    target_type = (
        reranker_type
        or getattr(settings, "RERANKER_TYPE", getattr(settings, "reranker_type", "disabled"))
        or "disabled"
    ).lower()
    target_model = model_name or getattr(
        settings, "RERANKER_MODEL", getattr(settings, "reranker_model", None)
    )

    if target_type in ("bge", "cross_encoder", "crossencoder", "sentence_transformers"):
        try:
            from app.ai.rag.reranker.cross_encoder_reranker import CrossEncoderReranker

            return (
                CrossEncoderReranker(model_name=target_model)
                if target_model
                else CrossEncoderReranker()
            )
        except Exception:
            return DisabledReranker()

    if target_type == "flashrank":
        try:
            from app.ai.rag.reranker.flashrank_reranker import FlashRankReranker

            return (
                FlashRankReranker(model_name=target_model)
                if target_model
                else FlashRankReranker()
            )
        except Exception:
            return DisabledReranker()

    return DisabledReranker()

