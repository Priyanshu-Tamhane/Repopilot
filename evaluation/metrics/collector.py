"""Benchmark metrics aggregation (Phase 2, Spec §16).

Computes accuracy / performance / inference / cost / agent-efficiency
metrics from a list of TaskResponse. Infrastructure metrics that need
workers/caching (queue latency, CPU/GPU, cache hit rate) are reserved
for Phase 6+ and reported as None.
"""
from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass
from typing import List, Optional

from api.schemas.tasks import TaskResponse


def _pctl(sorted_vals: list[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    k = max(0, min(len(sorted_vals) - 1, int(round((pct / 100) * (len(sorted_vals) - 1)))))
    return sorted_vals[k]


@dataclass
class BenchmarkMetrics:
    # Accuracy
    total: int
    successes: int
    success_rate: float
    test_pass_rate: float
    patch_rate: float  # fraction with non-empty patch (correctness proxy P2)
    # Performance (seconds)
    avg_latency: float
    median_latency: float
    p95_latency: float
    # Inference
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    avg_tokens_per_task: float
    total_llm_calls: int
    avg_llm_calls_per_task: float
    # Cost
    total_cost: float
    cost_per_task: float
    cost_per_success: Optional[float]
    # Agent efficiency
    avg_tool_calls_per_task: float
    total_errors: int
    # Infrastructure (Phase 2: only throughput measurable)
    tasks_per_minute: Optional[float]
    queue_latency: Optional[float] = None  # Phase 6
    cache_hit_rate: Optional[float] = None  # Phase 6

    def to_dict(self) -> dict:
        return asdict(self)


def aggregate(results: List[TaskResponse], wall_seconds: Optional[float] = None) -> BenchmarkMetrics:
    if not results:
        return BenchmarkMetrics(
            total=0, successes=0, success_rate=0.0, test_pass_rate=0.0, patch_rate=0.0,
            avg_latency=0.0, median_latency=0.0, p95_latency=0.0,
            total_input_tokens=0, total_output_tokens=0, total_tokens=0,
            avg_tokens_per_task=0.0, total_llm_calls=0, avg_llm_calls_per_task=0.0,
            total_cost=0.0, cost_per_task=0.0, cost_per_success=None,
            avg_tool_calls_per_task=0.0, total_errors=0, tasks_per_minute=None,
        )
    total = len(results)
    successes = sum(1 for r in results if r.success)
    passed = sum(r.tests_passed for r in results)
    failed = sum(r.tests_failed for r in results)
    denom = passed + failed

    lat = sorted(r.duration_seconds for r in results)
    in_tok = sum(r.input_tokens for r in results)
    out_tok = sum(r.output_tokens for r in results)
    llm_calls = sum(r.llm_calls for r in results)
    total_cost = sum(r.estimated_cost for r in results)

    return BenchmarkMetrics(
        total=total,
        successes=successes,
        success_rate=successes / total,
        test_pass_rate=(passed / denom) if denom else 0.0,
        patch_rate=sum(1 for r in results if r.patch.strip()) / total,
        avg_latency=sum(lat) / total,
        median_latency=statistics.median(lat),
        p95_latency=_pctl(lat, 95),
        total_input_tokens=in_tok,
        total_output_tokens=out_tok,
        total_tokens=in_tok + out_tok,
        avg_tokens_per_task=(in_tok + out_tok) / total,
        total_llm_calls=llm_calls,
        avg_llm_calls_per_task=llm_calls / total,
        total_cost=round(total_cost, 4),
        cost_per_task=round(total_cost / total, 4),
        cost_per_success=round(total_cost / successes, 4) if successes else None,
        avg_tool_calls_per_task=sum(r.tool_calls for r in results) / total,
        total_errors=sum(1 for r in results if r.error),
        tasks_per_minute=round(total / (wall_seconds / 60), 2) if wall_seconds else None,
    )
