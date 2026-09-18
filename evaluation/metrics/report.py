"""Markdown report renderer for benchmark results (Phase 2)."""
from __future__ import annotations

from api.schemas.tasks import TaskResponse
from .collector import BenchmarkMetrics


def render_markdown(
    experiment: str,
    dataset: str,
    metrics: BenchmarkMetrics,
    results: list[TaskResponse],
    task_ids: list[str],
) -> str:
    m = metrics
    lines = [
        f"# Benchmark Report - {experiment}",
        "",
        f"Dataset: `{dataset}` | Tasks: {m.total} | Successes: {m.successes}",
        "",
        "## Summary (Spec Sec.16)",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Task success rate | {m.success_rate:.1%} |",
        f"| Test pass rate | {m.test_pass_rate:.1%} |",
        f"| Patch rate | {m.patch_rate:.1%} |",
        f"| Avg latency | {m.avg_latency:.2f}s |",
        f"| Median latency | {m.median_latency:.2f}s |",
        f"| P95 latency | {m.p95_latency:.2f}s |",
        f"| Total tokens (in/out) | {m.total_tokens} ({m.total_input_tokens}/{m.total_output_tokens}) |",
        f"| Avg tokens/task | {m.avg_tokens_per_task:.0f} |",
        f"| LLM calls (total/avg) | {m.total_llm_calls}/{m.avg_llm_calls_per_task:.1f} |",
        f"| Cost/task | ${m.cost_per_task:.4f} |",
        f"| Cost/success | {'$%.4f' % m.cost_per_success if m.cost_per_success is not None else 'n/a'} |",
        f"| Avg tool calls/task | {m.avg_tool_calls_per_task:.1f} |",
        f"| Errors | {m.total_errors} |",
        f"| Tasks/min | {m.tasks_per_minute if m.tasks_per_minute is not None else 'n/a'} |",
        "",
        "## Per-task",
        "",
        "| Task | Success | Passed | Failed | Latency (s) | Tokens | LLM calls | Tool calls | Cost |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for tid, r in zip(task_ids, results):
        mark = "PASS" if r.success else "FAIL"
        lines.append(
            f"| {tid} | {mark} | {r.tests_passed} | {r.tests_failed} | "
            f"{r.duration_seconds:.2f} | {r.input_tokens + r.output_tokens} | "
            f"{r.llm_calls} | {r.tool_calls} | ${r.estimated_cost:.4f} |"
        )
    lines.append("")
    return "\n".join(lines)
