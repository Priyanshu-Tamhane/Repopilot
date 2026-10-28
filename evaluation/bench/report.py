"""RepoPilot - Offline Benchmark Report Generator (Phase 4).

Generates comprehensive Markdown & JSON evaluation reports directly from
saved raw Per-Run JSON records. Zero model re-invocations or network calls.
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from evaluation.bench.schema import BenchmarkRunRecord


@dataclass
class ConfigSummary:
    config_name: str
    model_id: str
    total_runs: int
    resolved_count: int
    resolve_rate: float
    avg_latency_s: float
    p95_latency_s: float
    total_tokens: int
    avg_tokens_per_task: int
    total_cost: float
    cost_per_resolved: float
    failure_breakdown: Dict[str, int]


def load_records_from_dir(results_dir: Path | str) -> List[BenchmarkRunRecord]:
    """Load all BenchmarkRunRecord JSON files in a results directory."""
    records: List[BenchmarkRunRecord] = []
    p = Path(results_dir)
    if not p.exists():
        return records

    for fpath in p.glob("*.json"):
        if fpath.name.startswith("summary"):
            continue
        try:
            rec = BenchmarkRunRecord.load(fpath)
            records.append(rec)
        except Exception:
            continue
    return records


def summarize_config_runs(config_name: str, runs: List[BenchmarkRunRecord]) -> ConfigSummary:
    """Compute aggregate statistical metrics for a single configuration."""
    total = len(runs)
    if total == 0:
        return ConfigSummary(
            config_name=config_name,
            model_id="",
            total_runs=0,
            resolved_count=0,
            resolve_rate=0.0,
            avg_latency_s=0.0,
            p95_latency_s=0.0,
            total_tokens=0,
            avg_tokens_per_task=0,
            total_cost=0.0,
            cost_per_resolved=0.0,
            failure_breakdown={},
        )

    resolved = sum(1 for r in runs if r.evaluation.resolved)
    resolve_rate = round((resolved / total) * 100, 1)

    latencies = [r.duration_seconds for r in runs]
    avg_latency = round(statistics.mean(latencies), 2)
    p95_latency = round(statistics.quantiles(latencies, n=20)[-1] if total >= 20 else max(latencies), 2)

    total_tokens = sum(r.input_tokens + r.output_tokens for r in runs)
    avg_tokens = int(total_tokens / total)

    total_cost = round(sum(r.estimated_cost for r in runs), 4)
    cost_per_resolved = round(total_cost / resolved, 4) if resolved > 0 else 0.0

    failures: Dict[str, int] = defaultdict(int)
    for r in runs:
        if not r.evaluation.resolved:
            cat = r.evaluation.failure_category or "unknown"
            failures[cat] += 1

    model_id = runs[0].model_id if runs else ""

    return ConfigSummary(
        config_name=config_name,
        model_id=model_id,
        total_runs=total,
        resolved_count=resolved,
        resolve_rate=resolve_rate,
        avg_latency_s=avg_latency,
        p95_latency_s=p95_latency,
        total_tokens=total_tokens,
        avg_tokens_per_task=avg_tokens,
        total_cost=total_cost,
        cost_per_resolved=cost_per_resolved,
        failure_breakdown=dict(failures),
    )


def generate_benchmark_report_markdown(results_dir: Path | str) -> str:
    """Generate reproducible GitHub Flavored Markdown report from results."""
    records = load_records_from_dir(results_dir)
    if not records:
        return "# RepoPilot Benchmark Report\n\nNo benchmark run records found."

    # Group runs by agent_config
    by_config: Dict[str, List[BenchmarkRunRecord]] = defaultdict(list)
    for r in records:
        by_config[r.agent_config].append(r)

    summaries: List[ConfigSummary] = []
    for cfg_name, cfg_runs in sorted(by_config.items()):
        summaries.append(summarize_config_runs(cfg_name, cfg_runs))

    lines = [
        "# RepoPilot — Official Benchmark Evaluation Report",
        "",
        "> Generated offline from raw per-run JSON records. Zero model re-invocations.",
        "",
        "## 1. Executive Summary & Configuration Comparison",
        "",
        "| Configuration | Model | Evaluated | Solved | Solve Rate (%) | Avg Latency (s) | Avg Tokens | Total Cost ($) | Cost / Solved ($) |",
        "| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]

    for s in summaries:
        lines.append(
            f"| **{s.config_name}** | `{s.model_id}` | {s.total_runs} | {s.resolved_count} | **{s.resolve_rate}%** | {s.avg_latency_s}s | {s.avg_tokens_per_task:,} | ${s.total_cost:.4f} | ${s.cost_per_resolved:.4f} |"
        )

    lines.extend([
        "",
        "## 2. Failure Mode Categorization",
        "",
        "| Configuration | Test Failures | Test Tampering | Patch Apply Failed | Timeouts | Other / Errors |",
        "| :--- | :---: | :---: | :---: | :---: | :---: |",
    ])

    for s in summaries:
        fb = s.failure_breakdown
        test_fail = fb.get("test_failed", 0)
        tamper = fb.get("test_tampering", 0)
        patch_fail = fb.get("patch_apply_failed", 0)
        timeout = fb.get("timeout", 0)
        other = sum(v for k, v in fb.items() if k not in ("test_failed", "test_tampering", "patch_apply_failed", "timeout"))
        lines.append(
            f"| **{s.config_name}** | {test_fail} | {tamper} | {patch_fail} | {timeout} | {other} |"
        )

    lines.extend([
        "",
        "## 3. Individual Task Run Log",
        "",
        "| Task ID | Config | Status | Duration (s) | Tokens (In/Out) | Cost ($) | Failure Category | Notes |",
        "| :--- | :--- | :---: | :---: | :---: | :---: | :--- | :--- |",
    ])

    for r in sorted(records, key=lambda x: (x.task_id, x.agent_config)):
        status_badge = "✅ PASSED" if r.evaluation.resolved else "❌ FAILED"
        fail_cat = r.evaluation.failure_category or "None"
        note = (r.evaluation.error or r.diagnostic_notes or "").replace("\n", " ")[:60]
        lines.append(
            f"| `{r.task_id}` | `{r.agent_config}` | {status_badge} | {r.duration_seconds}s | {r.input_tokens}/{r.output_tokens} | ${r.estimated_cost:.5f} | `{fail_cat}` | {note} |"
        )

    lines.append("")
    return "\n".join(lines)


def write_report(results_dir: Path | str, out_file: Path | str = "report.md") -> Path:
    """Read results and write Markdown report file."""
    md = generate_benchmark_report_markdown(results_dir)
    out_path = Path(out_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")
    return out_path
