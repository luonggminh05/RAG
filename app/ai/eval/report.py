import json
import logging
import os
from typing import Any, Dict, List
from rich.console import Console
from rich.table import Table

logger = logging.getLogger(__name__)

class EvalReport:
    """Báo cáo đánh giá chất lượng RAG (Rich Console & JSON output)."""

    def __init__(self, suite_name: str, results: List[Dict[str, Any]]):
        self.suite_name = suite_name
        self.results = results
        self.console = Console()

    def calculate_averages(self) -> Dict[str, float]:
        if not self.results:
            return {}

        metric_sums: Dict[str, float] = {}
        metric_counts: Dict[str, int] = {}

        for res in self.results:
            scores = res.get("scores", {})
            for m_name, val in scores.items():
                metric_sums[m_name] = metric_sums.get(m_name, 0.0) + val
                metric_counts[m_name] = metric_counts.get(m_name, 0) + 1

        return {
            m: round(metric_sums[m] / metric_counts[m], 4)
            for m in metric_sums
        }

    def print_summary(self) -> None:
        table = Table(title=f"📊 KẾT QUẢ ĐÁNH GIÁ: {self.suite_name.upper()}")
        table.add_column("Case ID", style="cyan", no_wrap=True)
        table.add_column("Query", style="white", max_width=40)

        # Lấy danh sách metrics từ case đầu tiên
        metric_names = []
        if self.results:
            metric_names = list(self.results[0].get("scores", {}).keys())

        for m in metric_names:
            table.add_column(m, style="green", justify="right")

        for r in self.results:
            row_data = [
                str(r.get("id")),
                str(r.get("query", ""))[:38] + "...",
            ]
            for m in metric_names:
                val = r.get("scores", {}).get(m, 0.0)
                # Tô màu nếu điểm thấp
                if "latency" in m:
                    row_data.append(f"{val:.2f}s")
                elif "hallucination" in m:
                    color = "red" if val > 0 else "green"
                    row_data.append(f"[{color}]{val * 100:.1f}%[/{color}]")
                else:
                    color = "green" if val >= 0.7 else "yellow" if val >= 0.4 else "red"
                    row_data.append(f"[{color}]{val * 100:.1f}%[/{color}]")
            table.add_row(*row_data)

        self.console.print(table)

        # In bảng tổng kết Averages
        avg_table = Table(title="📈 ĐIỂM SỐ TRUNG BÌNH (OVERALL)")
        avg_table.add_column("Chỉ số (Metric)", style="cyan")
        avg_table.add_column("Điểm trung bình", style="bold green", justify="right")

        averages = self.calculate_averages()
        for m, avg_val in averages.items():
            if "latency" in m:
                avg_table.add_row(m, f"{avg_val:.2f}s")
            elif "hallucination" in m:
                avg_table.add_row(m, f"{avg_val * 100:.2f}%")
            else:
                avg_table.add_row(m, f"{avg_val * 100:.2f}%")

        self.console.print(avg_table)

    def save_json(self, file_path: str) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
        data = {
            "suite": self.suite_name,
            "total_cases": len(self.results),
            "averages": self.calculate_averages(),
            "details": self.results,
        }
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self.console.print(f"[bold green]✔ Báo cáo đã lưu tại:[/bold green] {file_path}")
