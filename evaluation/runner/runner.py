"""Benchmark runner (Phase 2, Spec §14).

Runs every task of a fixed dataset against ONE agent architecture and
persists comparable results. Sequential execution only — parallel
workers arrive in Phase 6. Takes an agent factory so Exps 1-6 can reuse
the same dataset and entry point.
"""
from __future__ import annotations

import asyncio
import json
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Optional

from agents.baseline.agent import BaselineAgent
from api.schemas.tasks import TaskResponse
from evaluation.datasets.schema import BenchmarkDataset, BenchmarkTask
from evaluation.datasets.seed import materialize
from evaluation.metrics.collector import BenchmarkMetrics, aggregate
from evaluation.metrics.report import render_markdown


def _resolve_llm(settings) -> tuple[str, str, str, str]:
    if settings.groq_api_key:
        return "groq", settings.groq_model, settings.groq_api_key, settings.groq_base_url
    elif settings.llm_provider == "groq":
        return "groq", settings.groq_model, settings.groq_api_key, settings.groq_base_url
    else:
        return settings.llm_provider, settings.openai_model, settings.openai_api_key, "https://api.openai.com/v1"


def build_baseline_agent() -> BaselineAgent:
    """Default factory: mirrors execution/queue/manager.py provider priority (Groq first)."""
    from api.dependencies.config import get_settings

    settings = get_settings()
    provider, model, api_key, base_url = _resolve_llm(settings)
    return BaselineAgent(
        workdir=settings.workdir,
        sandbox_mode=settings.sandbox_mode,
        use_mock=settings.llm_mock,
        model=model,
        api_key=api_key,
        provider=provider,
        base_url=base_url,
    )


def build_retrieval_agent(top_k: int = 6, char_budget: int = 8000) -> BaselineAgent:
    """Factory for Exp2 — same LLM but with RAG retrieval enabled."""
    from api.dependencies.config import get_settings

    settings = get_settings()
    provider, model, api_key, base_url = _resolve_llm(settings)
    return BaselineAgent(
        workdir=settings.workdir,
        sandbox_mode=settings.sandbox_mode,
        use_mock=settings.llm_mock,
        model=model,
        api_key=api_key,
        provider=provider,
        base_url=base_url,
        use_retrieval=True,
        retrieval_top_k=top_k,
        retrieval_budget=char_budget,
    )


class BenchmarkRunner:
    def __init__(
        self,
        agent_factory: Callable[[], BaselineAgent] = build_baseline_agent,
        sandbox_mode: Optional[str] = None,  # None = use agent default
        timeout_s: float = 300.0,
    ):
        self.agent_factory = agent_factory
        self.sandbox_mode = sandbox_mode
        self.timeout_s = timeout_s

    async def run_task(self, task: BenchmarkTask, repo_parent: Path) -> TaskResponse:
        repo = materialize(task, repo_parent)
        agent = self.agent_factory()
        if self.sandbox_mode:
            agent.sandbox_mode = self.sandbox_mode
        try:
            result = await asyncio.wait_for(agent.run(str(repo), task.issue), timeout=self.timeout_s)
        except asyncio.TimeoutError:
            result = TaskResponse(
                success=False, duration_seconds=self.timeout_s,
                error=f"task {task.id} timed out after {self.timeout_s}s",
            )
        if result.trace is None:
            result.trace = {}
        result.trace["benchmark_task_id"] = task.id
        result.trace["benchmark_category"] = task.category
        return result

    async def run_all(
        self, dataset: BenchmarkDataset, limit: Optional[int] = None
    ) -> tuple[list[str], list[TaskResponse], float]:
        tasks = dataset.tasks[:limit] if limit else dataset.tasks
        task_ids: list[str] = []
        results: list[TaskResponse] = []
        wall_start = time.time()
        with tempfile.TemporaryDirectory(prefix="repopilot-bench-") as td:
            for task in tasks:
                print(f"[{task.id}/{dataset.tasks[-1].id}] {task.category} ...", flush=True)
                result = await self.run_task(task, Path(td))
                mark = "PASS" if result.success else "FAIL"
                print(f"  {mark} passed={result.tests_passed} failed={result.tests_failed} "
                      f"{result.duration_seconds:.1f}s", flush=True)
                task_ids.append(task.id)
                results.append(result)
        return task_ids, results, time.time() - wall_start


def run_experiment(
    experiment: str,
    dataset: BenchmarkDataset,
    task_ids: list[str],
    results: list[TaskResponse],
    wall_seconds: float,
    output_dir: str | Path,
) -> tuple[BenchmarkMetrics, Path, Path]:
    """Aggregate, persist JSON + markdown report. Returns (metrics, json_path, md_path)."""
    metrics = aggregate(results, wall_seconds=wall_seconds)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    json_path = out / f"{experiment}_{stamp}.json"
    md_path = out / f"{experiment}_{stamp}.md"

    payload = {
        "experiment": experiment,
        "dataset": {"name": dataset.name, "version": dataset.version, "tasks": dataset.ids()},
        "wall_seconds": round(wall_seconds, 2),
        "metrics": metrics.to_dict(),
        "results": [
            {
                "task_id": tid,
                "success": r.success,
                "patch_chars": len(r.patch),
                "tests_passed": r.tests_passed,
                "tests_failed": r.tests_failed,
                "duration_seconds": r.duration_seconds,
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "llm_calls": r.llm_calls,
                "tool_calls": r.tool_calls,
                "estimated_cost": r.estimated_cost,
                "error": (r.error[:500] if r.error else None),
            }
            for tid, r in zip(task_ids, results)
        ],
    }
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_path.write_text(
        render_markdown(experiment, f"{dataset.name} v{dataset.version}", metrics, results, task_ids),
        encoding="utf-8",
    )
    return metrics, json_path, md_path
