"""
Unit tests kiểm tra toàn bộ các cải tiến mới trong RAG project:
1. BaseReranker & DisabledReranker (rerank_with_scores)
2. get_reranker factory
3. VietnameseNormalizer (bank_acronyms.json, junk filter, elongation, normalize_for_match)
4. DocumentRepository._build_fts_query & get_adjacent_chunks
5. VectorRetriever (dynamic top-k, citation rerank_score, adjacent expansion)
"""

try:
    import pytest
except ImportError:
    pytest = None
import asyncio
from unittest.mock import AsyncMock, MagicMock
from app.ai.rag.reranker.base import BaseReranker
from app.ai.rag.reranker.disabled import DisabledReranker
from app.ai.rag.reranker.factory import get_reranker
from app.ai.rag.text.normalizer import VietnameseNormalizer, normalize_for_match
from app.modules.document.repository import DocumentRepository
from app.ai.rag.retrieval.retriever import VectorRetriever


def test_base_reranker_and_disabled():
    reranker = DisabledReranker()
    chunks = ["Chunk A", "Chunk B", "Chunk C"]
    ranked = reranker.rerank("query", chunks, top_k=2)
    assert ranked == [0, 1]

    scored = reranker.rerank_with_scores("query", chunks, top_k=2)
    assert len(scored) == 2
    assert scored[0] == (0, 1.0)        # 1.0 / (1.0 + 0)
    assert scored[1] == (1, 0.5)        # 1.0 / (1.0 + 1)


def test_reranker_factory():
    # Disabled reranker
    r_disabled = get_reranker("disabled")
    assert isinstance(r_disabled, DisabledReranker)

    # Unknown type should fallback to DisabledReranker safely
    r_unknown = get_reranker("non_existent_type")
    assert isinstance(r_unknown, DisabledReranker)


def test_vietnamese_normalizer_improvements():
    # 1. Mở rộng từ viết tắt ngân hàng
    raw = "STK và HDTD của KH tại PGD"
    norm = VietnameseNormalizer.normalize(raw, expand_acronyms=True)
    assert "Số tài khoản" in norm
    assert "Hợp đồng tín dụng" in norm
    assert "Khách hàng" in norm
    assert "Phòng giao dịch" in norm

    # 2. Nhận diện Giai đoạn (GD + số)
    phase_text = "Thực hiện theo GD 2 của dự án"
    norm_phase = VietnameseNormalizer.normalize(phase_text, expand_acronyms=True)
    assert "Giai đoạn 2" in norm_phase

    # 3. Khử lặp ký tự kéo dài
    elongated = "Dự ánnnnn này rất tốt"
    norm_elong = VietnameseNormalizer.normalize(elongated, expand_acronyms=False)
    assert "Dự án" in norm_elong and "Dự ánnnnn" not in norm_elong

    # 4. Lọc ký tự rác và dấu cảm thán
    junk = "Thông báo quan trọng!!! @#$%^&*"
    norm_junk = VietnameseNormalizer.normalize(junk)
    assert "!" not in norm_junk
    assert "@" not in norm_junk

    # 5. normalize_for_match
    match_str = normalize_for_match("Hợp Đồng Tín Dụng ĐKKD 2026")
    assert match_str == "hop dong tin dung dkkd 2026"


def test_fts_query_builder():
    # Query có mã số >= 4 số và stopwords
    query = "quy trình thanh toán cho hợp đồng số 202688 là gì và như thế nào"
    fts = DocumentRepository._build_fts_query(query)

    # 202688 phải đứng đầu
    assert fts.startswith('"202688"')
    # Stopwords "cho", "là", "gì", "và", "như", "thế", "nào" bị lọc
    terms = fts.split(" OR ")
    assert '"202688"' in terms
    assert '"hợp"' in terms or '"đồng"' in terms or '"quy"' in terms
    assert '"là"' not in terms
    assert '"và"' not in terms


def test_document_repository_adjacent_chunks():
    repo = DocumentRepository()
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    repo._get_raw_connection = MagicMock(return_value=mock_conn)

    import json
    mock_cursor.fetchall.return_value = [
        ("id_1", "Chunk 1 content", json.dumps({"backend_id": "42", "chunk_index": 1})),
        ("id_2", "Chunk 2 content", json.dumps({"backend_id": "42", "chunk_index": 2})),
    ]

    adj = repo.get_adjacent_chunks(backend_id="42", chunk_indices=[1, 2])
    assert len(adj) == 2
    assert adj[0]["id"] == "id_1"
    assert adj[0]["metadata"]["chunk_index"] == 1
    assert adj[1]["id"] == "id_2"


def test_vector_retriever_with_rerank_scores():
    mock_repo = MagicMock()
    mock_repo.search.return_value = {
        "ids": [["c1", "c2"]],
        "documents": [["Doc content 1", "Doc content 2"]],
        "metadatas": [[{"source": "doc.pdf", "page": 1}, {"source": "doc.pdf", "page": 2}]],
        "distances": [[0.1, 0.2]],
        "citations": [[{"source": "doc.pdf", "page": 1}, {"source": "doc.pdf", "page": 2}]],
    }

    mock_embed = MagicMock()
    mock_embed.embed_query_cached = AsyncMock(return_value=([0.1] * 1024, True))

    retriever = VectorRetriever(
        repository=mock_repo,
        embedding_service=mock_embed,
        reranker=DisabledReranker(),
    )

    async def _run():
        res = await retriever.retrieve_context(
            query="hướng dẫn thủ tục mở tài khoản",
            top_k=2,
            user_roles="User",
            user_department="IT",
        )
        assert "citations" in res
        assert "query_analysis" in res
        citations = res["citations"][0]
        # rerank_score được ghi vào citations
        assert "rerank_score" in citations[0]
        assert citations[0]["rerank_score"] == 1.0
        assert citations[1]["rerank_score"] == 0.5
        assert res["query_analysis"]["recommended_top_k"] > 0

    asyncio.run(_run())
