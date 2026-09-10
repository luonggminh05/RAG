import argparse
import asyncio
import json
import os
import sys

# Ensure UTF-8 stdout encoding on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Add project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.ai.eval.runner import EvalRunner
from app.routers.dependencies import get_vector_retriever
from app.llmops.factory import get_chat_model

def load_cases(file_path: str) -> list:
    if not os.path.exists(file_path):
        print(f"Error: Test cases file not found: {file_path}")
        return []
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)

async def main():
    parser = argparse.ArgumentParser(description="RAG System Quality Evaluation Benchmark")
    parser.add_argument(
        "--suite",
        choices=["retrieval", "generation", "all"],
        default="all",
        help="Evaluation suite to run (retrieval | generation | all)",
    )
    parser.add_argument(
        "--fail-under",
        type=float,
        default=0.0,
        help="Minimum overall score percentage threshold to pass (e.g. 75.0)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="reports/eval_report.json",
        help="File path to save JSON evaluation report",
    )
    args = parser.parse_args()

    retriever = None
    try:
        retriever = get_vector_retriever()
    except Exception as ex:
        print(f"[NOTE] VectorRetriever DB connection skipped or offline: {ex}")

    llm = None
    try:
        llm = get_chat_model()
    except Exception as ex:
        print(f"[NOTE] LLM initialization for eval skipped: {ex}")

    runner = EvalRunner(retriever=retriever, llm=llm)
    suites_to_run = ["retrieval", "generation"] if args.suite == "all" else [args.suite]

    all_passed = True
    overall_scores = []

    for suite_name in suites_to_run:
        cases_file = os.path.join(PROJECT_ROOT, "tests", "eval", "cases", f"{suite_name}_cases.json")
        cases = load_cases(cases_file)
        if not cases:
            print(f"Warning: No cases loaded for {suite_name}")
            continue

        if suite_name == "retrieval":
            report = await runner.run_retrieval_suite(cases)
        else:
            report = await runner.run_generation_suite(cases)

        report.print_summary()
        report_path = args.output.replace(".json", f"_{suite_name}.json")
        report.save_json(report_path)

        # Check threshold
        averages = report.calculate_averages()
        for m, score in averages.items():
            if "latency" not in m:
                overall_scores.append(score * 100.0)

    if args.fail_under > 0 and overall_scores:
        avg_score = sum(overall_scores) / len(overall_scores)
        print(f"\nTarget Threshold: {args.fail_under:.1f}% | Achieved Score: {avg_score:.1f}%")
        if avg_score < args.fail_under:
            print(f"❌ FAILED: Overall evaluation score {avg_score:.1f}% is under {args.fail_under:.1f}%!")
            sys.exit(1)
        else:
            print(f"✅ PASSED: Evaluation threshold met successfully!")

if __name__ == "__main__":
    asyncio.run(main())
