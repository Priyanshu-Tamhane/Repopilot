"""Stub for Phase 2 metrics collector. Phase 1 records metrics per task in TaskResponse already."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from api.schemas.tasks import TaskResponse


@dataclass
class BenchmarkMetrics:
    total: int
    success_rate: float
    avg_latency: float
    avg_tokens: float
    avg_cost: float
    test_pass_rate: float


def aggregate(results: List[TaskResponse]) -> BenchmarkMetrics:
    if not results:
        return BenchmarkMetrics(0, 0, 0, 0, 0, 0)
    success = sum(1 for r in results if r.success)
    total = len(results)
    avg_lat = sum(r.duration_seconds for r in results) / total
    avg_tok = sum(r.input_tokens + r.output_tokens for r in results) / total
    avg_cost = sum(r.estimated_cost for r in results) / total
    total_tests = sum(r.tests_passed + r.tests_failed for r in results)
    passed = sum(r.tests_passed for r in results)
    pass_rate = (passed / total_tests) if total_tests else 0
    return BenchmarkMetrics(
        total=total,
        success_rate=success / total,
        avg_latency=avg_lat,
        avg_tokens=avg_tok,
        avg_cost=avg_cost,
        test_pass_rate=pass_rate,
    )
