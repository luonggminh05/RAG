import logging
from typing import Any, Dict, List
from app.ai.eval.metrics import BaseMetric

logger = logging.getLogger(__name__)

class EvalScorer:
    """Chấm điểm kết quả của 1 test case dựa trên danh sách các metrics."""

    def __init__(self, metrics: List[BaseMetric]):
        self.metrics = metrics

    async def score(
        self,
        case: Dict[str, Any],
        output: Dict[str, Any],
    ) -> Dict[str, Any]:
        case_id = case.get("id", "unknown_case")
        scores: Dict[str, float] = {}

        for metric in self.metrics:
            try:
                val = await metric.evaluate(case, output)
                scores[metric.name] = val
            except Exception as ex:
                logger.warning(f"[EVAL] Error evaluating metric '{metric.name}' for case '{case_id}': {ex}")
                scores[metric.name] = 0.0

        return {
            "id": case_id,
            "query": case.get("query", ""),
            "scores": scores,
            "output_preview": str(output.get("answer", "") or output.get("documents", [""]))[:120],
        }
