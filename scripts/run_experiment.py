"""
Script chạy benchmark và so sánh A/B các thành phần trong RAG Fast Pipeline:
1. Supervisor Router (Rule-based vs Structured Output)
2. Dynamic Top-K Query Analyzer (Accuracy & Latency)
3. Fast Pipeline LangGraph (Latency & Token Streaming)
"""

import asyncio
import json
import os
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.ai.agent.supervisor.classifier import IntentClassifier
from app.ai.rag.retrieval.query_analyzer import determine_dynamic_top_k


def load_test_cases():
    cases_file = os.path.join(
        PROJECT_ROOT, "app", "ai", "agent", "agentic_rag", "eval", "eval_cases.json"
    )
    if not os.path.exists(cases_file):
        print(f"Test cases file not found: {cases_file}")
        return []
    with open(cases_file, "r", encoding="utf-8") as f:
        return json.load(f)


async def evaluate_classifier_and_analyzer():
    cases = load_test_cases()
    if not cases:
        return

    classifier = IntentClassifier()
    print("=" * 70)
    print("📊 BENCHMARK: SUPERVISOR ROUTER & DYNAMIC TOP-K ANALYZER")
    print("=" * 70)

    correct_intent = 0
    correct_category = 0
    total = len(cases)

    for case in cases:
        query = case["query"]
        expected_intent = case.get("expected_intent")
        expected_cat = case.get("expected_category")

        t0 = time.perf_counter()
        intent_res = await classifier.classify(query)
        t_intent = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        top_k, analysis = determine_dynamic_top_k(query)
        t_analyzer = (time.perf_counter() - t0) * 1000

        is_intent_ok = intent_res.intent == expected_intent
        is_cat_ok = analysis.category.value == expected_cat

        if is_intent_ok:
            correct_intent += 1
        if is_cat_ok:
            correct_category += 1

        status_intent = "✅" if is_intent_ok else "❌"
        status_cat = "✅" if is_cat_ok else "⚠️"

        print(f"\n[Case: {case['id']}] '{query[:60]}...'")
        print(f"  • Intent: {status_intent} {intent_res.intent} (expected: {expected_intent}) | {t_intent:.2f}ms")
        print(f"  • Category: {status_cat} {analysis.category.value} -> Top-K={top_k} (expected: {expected_cat}) | {t_analyzer:.2f}ms")

    print("\n" + "=" * 70)
    print(f"🎯 KẾT QUẢ ĐÁNH GIÁ TỔNG QUAN:")
    print(f"  - Intent Router Accuracy: {correct_intent}/{total} ({correct_intent/total*100:.1f}%)")
    print(f"  - Dynamic Top-K Accuracy: {correct_category}/{total} ({correct_category/total*100:.1f}%)")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(evaluate_classifier_and_analyzer())
