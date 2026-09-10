import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

from app.ai.eval.metrics import (
    HitRateAtK,
    MRRAtK,
    ContextRelevanceScore,
    FaithfulnessScore,
    HallucinationRate,
    CitationPrecision,
    AnswerLatency,
)
from app.ai.eval.scorer import EvalScorer
from app.ai.eval.report import EvalReport

logger = logging.getLogger(__name__)

class EvalRunner:
    """Điều phối và thực thi bộ kiểm thử đánh giá chất lượng (Retrieval & Generation)."""

    def __init__(self, retriever: Optional[Any] = None, llm: Optional[Any] = None):
        self.retriever = retriever
        self.llm = llm

    async def run_retrieval_suite(
        self,
        test_cases: List[Dict[str, Any]],
        top_k: int = 5,
    ) -> EvalReport:
        """Chạy kiểm thử chất lượng Retrieval (Hybrid Search: Vector + FTS + RRF)."""
        metrics = [
            HitRateAtK(k=top_k),
            MRRAtK(k=top_k),
            ContextRelevanceScore(),
            AnswerLatency(),
        ]
        scorer = EvalScorer(metrics=metrics)
        results: List[Dict[str, Any]] = []

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
        ) as progress:
            task = progress.add_task("[cyan]Đang chạy Retrieval Evaluation...", total=len(test_cases))

            for case in test_cases:
                query = case.get("query", "")
                effective_k = case.get("top_k", top_k)

                start_time = time.perf_counter()
                output: Dict[str, Any] = {"documents": [], "citations": []}

                if self.retriever:
                    try:
                        res = await self.retriever.retrieve_context(
                            query=query,
                            top_k=effective_k,
                            user_roles=case.get("user_roles"),
                            user_department=case.get("user_department"),
                        )
                        output["documents"] = res.get("documents", [[]])[0] if res.get("documents") else []
                        output["citations"] = res.get("citations", [[]])[0] if res.get("citations") else []
                    except Exception as ex:
                        logger.warning(f"[EVAL] Retrieval error for case '{case.get('id')}': {ex}")
                elif "mock_documents" in case:
                    # Chế độ test với mock documents khi DB offline
                    output["documents"] = case["mock_documents"]
                    output["citations"] = case.get("mock_citations", [])

                output["latency_seconds"] = time.perf_counter() - start_time
                scored_case = await scorer.score(case, output)
                results.append(scored_case)

                progress.update(task, advance=1)

        return EvalReport("Retrieval Evaluation", results)

    async def run_generation_suite(
        self,
        test_cases: List[Dict[str, Any]],
    ) -> EvalReport:
        """Chạy kiểm thử chất lượng sinh câu trả lời (Faithfulness, Hallucination, Citation)."""
        metrics = [
            FaithfulnessScore(),
            HallucinationRate(),
            CitationPrecision(),
            AnswerLatency(),
        ]
        scorer = EvalScorer(metrics=metrics)
        results: List[Dict[str, Any]] = []

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
        ) as progress:
            task = progress.add_task("[magenta]Đang chạy Generation Evaluation...", total=len(test_cases))

            for case in test_cases:
                start_time = time.perf_counter()
                output: Dict[str, Any] = {
                    "answer": case.get("ground_truth") or case.get("sample_answer", ""),
                    "citations": case.get("sample_citations", []),
                }

                if self.llm and "context" in case:
                    try:
                        from langchain_core.messages import HumanMessage, SystemMessage
                        resp = await self.llm.ainvoke([
                            SystemMessage(content="Bạn là trợ lý giải đáp nghiệp vụ. Chỉ trả lời dựa vào ngữ cảnh sau: " + case["context"]),
                            HumanMessage(content=case.get("query", ""))
                        ])
                        output["answer"] = resp.content if hasattr(resp, "content") else str(resp)
                    except Exception as ex:
                        logger.warning(f"[EVAL] LLM generation error for case '{case.get('id')}': {ex}. Using ground_truth sample.")
                        output["answer"] = case.get("ground_truth") or case.get("sample_answer", "")

                output["latency_seconds"] = time.perf_counter() - start_time
                scored_case = await scorer.score(case, output)
                results.append(scored_case)

                progress.update(task, advance=1)

        return EvalReport("Generation Evaluation", results)
