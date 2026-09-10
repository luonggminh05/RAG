import asyncio
import pytest
from app.security.rate_limiter import RateLimiter, resolve_role_for_rate_limit
from app.ai.agent.supervisor.classifier import IntentClassifier
from app.ai.rag.query.contextualizer import QueryContextualizer
from app.ai.rag.chunking.splitter import TextChunker
from app.ai.eval.metrics import HitRateAtK, MRRAtK, CitationPrecision
from app.llmops.langfuse import setup_langfuse, get_langfuse_callback_handler, log_feedback_score

def test_rate_limiter_and_roles():
    limiter = RateLimiter()
    
    # Check role resolution
    assert resolve_role_for_rate_limit("admin,user") == "Admin"
    assert resolve_role_for_rate_limit("manager") == "Elite"
    assert resolve_role_for_rate_limit("guest") == "Officer"
    
    # Check sliding window
    async def _test():
        allowed, limit, remaining, retry_after = await limiter.check_rate_limit("user_test", "Officer")
        assert allowed is True
        assert remaining == limit - 1
        assert retry_after == 60
    
    asyncio.run(_test())


def test_intent_classifier():
    classifier = IntentClassifier()
    
    async def _test():
        # Rule-based greetings
        r_hello = await classifier.classify("Xin chào bạn, bạn là ai thế?")
        assert r_hello.intent == "chitchat"
        assert r_hello.confidence >= 0.8
        
        # Rule-based gratitude
        r_thanks = await classifier.classify("Cảm ơn bạn rất nhiều")
        assert r_thanks.intent == "chitchat"
        
        # RAG / Technical query
        r_rag = await classifier.classify("Quy định điều chuyển tài sản cố định áp dụng khi nào?")
        assert r_rag.intent == "rag"

    asyncio.run(_test())


def test_query_contextualizer():
    contextualizer = QueryContextualizer()
    async def _test():
        # Empty history returns original query
        q = await contextualizer.rewrite("Tài sản đó là gì?", [])
        assert q == "Tài sản đó là gì?"
    asyncio.run(_test())


def test_hierarchical_chunking():
    chunker = TextChunker()
    text = (
        "# I. QUY ĐỊNH BẢO TRÌ\n\n"
        "Tài sản cố định cần được bảo dưỡng định kỳ hàng quý bởi phòng kỹ thuật.\n"
        "Chi phí bảo dưỡng được hạch toán vào chi phí quản lý vận hành của đơn vị.\n"
        "Mọi hỏng hóc phát sinh ngoài dự toán phải lập biên bản báo cáo Giám đốc phê duyệt.\n" * 10
    )
    pairs = chunker.split_hierarchical(text, parent_chunk_size=500, child_chunk_size=150)
    assert len(pairs) > 0
    # Every pair contains child and parent
    for child, parent in pairs:
        assert "parent_content" in child.metadata
        assert child.metadata["parent_content"] == parent.text
        assert len(parent.text) >= len(child.text)


def test_eval_metrics():
    async def _test():
        # HitRateAtK
        case_hit = {"expected_source_keywords": ["tài sản"]}
        output_hit = {"documents": ["Quy định quản lý tài sản cố định"]}
        hit = await HitRateAtK(k=3).evaluate(case_hit, output_hit)
        assert hit == 1.0

        case_miss = {"expected_source_keywords": ["nghỉ phép"]}
        miss = await HitRateAtK(k=3).evaluate(case_miss, output_hit)
        assert miss == 0.0

        # MRRAtK
        mrr = await MRRAtK(k=3).evaluate(case_hit, output_hit)
        assert mrr == 1.0

        # CitationPrecision
        case_cit = {}
        output_cit = {
            "answer": "Theo tài liệu [doc_1.pdf], tài sản phải kiểm kê.",
            "citations": [{"source": "doc_1.pdf"}]
        }
        cp = await CitationPrecision().evaluate(case_cit, output_cit)
        assert cp == 1.0

    asyncio.run(_test())


def test_langfuse_helpers():
    setup_langfuse()
    handler = get_langfuse_callback_handler()
    # If not configured, should return None safely without raising
    log_feedback_score(name="user_feedback", value=1.0, comment="Test")


def test_pipeline_langfuse_spans_and_hierarchical():
    """Kiểm tra IngestionPipeline tạo đúng spans Langfuse và hỗ trợ hierarchical chunking."""
    from unittest.mock import AsyncMock, MagicMock, patch
    from app.ai.rag.ingestion.pipeline import IngestionPipeline
    from app.ai.rag.ingestion.extractor import IngestedDocument

    repo = MagicMock()
    embed_svc = MagicMock()
    embed_svc.embed_texts = AsyncMock(return_value=[[0.1] * 1024, [0.2] * 1024])

    pipeline = IngestionPipeline(repository=repo, embedding_service=embed_svc)

    # Mock extractor to return test doc
    sample_text = (
        "# I. QUY TRÌNH MUA SẮM\n\n"
        "Đơn vị lập phiếu yêu cầu mua sắm thiết bị văn phòng gửi phòng hành chính.\n" * 5
    )
    mock_doc = IngestedDocument(
        page_content=sample_text,
        metadata={"page": 1}
    )
    pipeline.extractor.extract = AsyncMock(return_value=[mock_doc])

    # Mock Langfuse client and trace
    mock_client = MagicMock()
    mock_trace = MagicMock()
    mock_span = MagicMock()
    mock_trace.span.return_value = mock_span
    mock_client.trace.return_value = mock_trace

    with patch("app.ai.rag.ingestion.pipeline.get_langfuse_client", return_value=mock_client), \
         patch("app.ai.rag.ingestion.pipeline.flush_langfuse"):

        async def _run():
            success, chunk_count = await pipeline._run_async(
                task_id="task_test_001",
                temp_path="dummy.txt",
                file_name="quy_trinh.txt",
                file_size=1024,
                metadata={"hierarchical": True, "backend_id": "42"}
            )
            assert success is True
            assert chunk_count > 0

            # Verify Langfuse spans were created for stages
            span_names = [call[1]["name"] for call in mock_trace.span.call_args_list if "name" in call[1]]
            assert "extract" in span_names
            assert "chunk" in span_names
            assert "embed" in span_names
            assert "upsert" in span_names

            # Verify span.end was called with metrics
            assert mock_span.end.call_count >= 4

            # Verify repository upsert was called with parent_chunk_ids
            repo.upsert_documents.assert_called_once()
            _, kwargs = repo.upsert_documents.call_args
            assert "parent_chunk_ids" in kwargs

        asyncio.run(_run())


def test_document_repository_parent_chunk_search():
    """Kiểm tra DocumentRepository.search join và trả về parent_content khi gặp child chunk."""
    import json
    from unittest.mock import MagicMock
    from app.modules.document.repository import DocumentRepository

    repo = DocumentRepository()

    # Create mock connection and cursor
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    repo._get_raw_connection = MagicMock(return_value=mock_conn)

    # Mock vector search returning a child chunk with parent_chunk_id
    child_id = "task_001_chunk_0"
    child_text = "Nội dung child chunk chi tiết"
    parent_id = "task_001_parent_0"
    parent_text = "Nội dung parent chunk đầy đủ ngữ cảnh cho LLM"
    child_meta = {"source": "policy.pdf", "page": 1}

    # Vector rows: (Id, Document, Metadata, Distance, ParentChunkId)
    mock_vector_rows = [
        (child_id, child_text, json.dumps(child_meta), 0.15, parent_id)
    ]
    # Parent fetch rows: (Id, Document)
    mock_parent_rows = [
        (parent_id, parent_text)
    ]

    def cursor_fetchall_side_effect():
        # First call is vector search, second call is FTS, third call is parent fetch
        if mock_cursor.execute.call_count == 1:
            return mock_vector_rows
        elif mock_cursor.execute.call_count == 2:
            return []  # No FTS rows
        else:
            return mock_parent_rows

    mock_cursor.fetchall.side_effect = cursor_fetchall_side_effect

    results = repo.search(
        query="mua sắm",
        query_embedding=[0.05] * repo.dims,
        top_k=3
    )

    # 1. LLM receives parent_content in documents
    assert len(results["documents"][0]) == 1
    assert results["documents"][0][0] == parent_text

    # 2. Citations keep child_content for debugging/verification
    citation = results["citations"][0][0]
    assert citation["child_content"] == child_text
    assert citation["parent_content"] == parent_text
    assert citation["parent_chunk_id"] == parent_id

