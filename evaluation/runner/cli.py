"""CLI: python -m evaluation.runner.cli [--limit 20] [--output-dir evaluation/results] [--retrieval]"""
from __future__ import annotations

import argparse
import asyncio

from evaluation.datasets.seed import build_dataset, load_json
from evaluation.experiments.exp1_baseline import EXPERIMENT
from evaluation.runner.runner import BenchmarkRunner, build_baseline_agent, build_retrieval_agent, run_experiment


def main() -> None:
    ap = argparse.ArgumentParser(description="RepoPilot benchmark runner (Phase 2)")
    ap.add_argument("--limit", type=int, default=None, help="max tasks to run")
    ap.add_argument("--output-dir", default="evaluation/results")
    ap.add_argument("--sandbox", default=None, help="auto|docker|local (default: agent settings)")
    ap.add_argument("--timeout", type=float, default=300.0, help="per-task timeout seconds")
    ap.add_argument("--dataset", default=None, help="path to dataset JSON (default: seed)")
    ap.add_argument("--experiment", default=EXPERIMENT["name"])
    ap.add_argument("--retrieval", action="store_true", help="enable RAG retrieval (Exp2)")
    ap.add_argument("--top-k", type=int, default=6)
    args = ap.parse_args()

    dataset = load_json(args.dataset) if args.dataset else build_dataset()
    if args.retrieval:
        # Use retrieval factory; override experiment name if default
        if args.experiment == EXPERIMENT["name"]:
            args.experiment = "exp2_retrieval"
        factory = lambda: build_retrieval_agent(top_k=args.top_k)
    else:
        factory = None
    runner = BenchmarkRunner(agent_factory=factory or build_baseline_agent, sandbox_mode=args.sandbox, timeout_s=args.timeout)
    task_ids, results, wall = asyncio.run(runner.run_all(dataset, limit=args.limit))
    metrics, json_path, md_path = run_experiment(
        args.experiment, dataset, task_ids, results, wall, args.output_dir
    )
    print(f"\n success={metrics.successes}/{metrics.total} "
          f"({metrics.success_rate:.0%}) avg_lat={metrics.avg_latency:.1f}s "
          f"cost/task=${metrics.cost_per_task:.4f}")
    print(f" wrote {json_path}\n wrote {md_path}")


if __name__ == "__main__":
    main()
