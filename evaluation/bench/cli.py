"""RepoPilot - Benchmark CLI (Phase 4).

Provides authoritative command line entry point:
    repopilot-bench run --dataset dataset/tasks.jsonl --agent b0 --out results/
    repopilot-bench report --results results/ --out report.md
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from evaluation.bench.harness import BenchmarkHarness
from evaluation.bench.report import write_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="repopilot-bench",
        description="RepoPilot Standardized Benchmark Harness & Report Generator (Phase 4)",
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="Benchmark action to perform")

    # --- RUN SUBCOMMAND ---
    run_parser = subparsers.add_parser("run", help="Run benchmark on dataset")
    run_parser.add_argument(
        "--dataset",
        type=str,
        default="dataset/tasks.jsonl",
        help="Path to tasks.jsonl dataset (default: dataset/tasks.jsonl)",
    )
    run_parser.add_argument(
        "--agent",
        type=str,
        default="b0",
        choices=["b0", "b1", "b2", "b3"],
        help="Agent configuration: b0 (baseline), b1 (retrieval), b2 (multi-agent), b3 (routing)",
    )
    run_parser.add_argument(
        "--model",
        type=str,
        default="openai/gpt-oss-120b",
        help="LLM model identifier (default: openai/gpt-oss-120b)",
    )
    run_parser.add_argument(
        "--provider",
        type=str,
        default="mock",
        choices=["mock", "groq", "openai"],
        help="LLM provider (default: mock)",
    )
    run_parser.add_argument(
        "--mock",
        action="store_true",
        default=True,
        help="Use deterministic mock heuristic (default: True for safe CI)",
    )
    run_parser.add_argument(
        "--out",
        type=str,
        default="evaluation/results",
        help="Output directory for raw JSON run records (default: evaluation/results)",
    )
    run_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of tasks to run (useful for pilot/smoke testing)",
    )

    # --- REPORT SUBCOMMAND ---
    report_parser = subparsers.add_parser("report", help="Generate report from saved run results")
    report_parser.add_argument(
        "--results",
        type=str,
        default="evaluation/results",
        help="Directory containing raw JSON run records (default: evaluation/results)",
    )
    report_parser.add_argument(
        "--out",
        type=str,
        default="evaluation/results/report.md",
        help="Target output markdown file path (default: evaluation/results/report.md)",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if not args.subcommand:
        parser.print_help()
        sys.exit(1)

    if args.subcommand == "run":
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)

        print("=" * 60)
        print(f"RepoPilot Benchmark Run — Configuration: {args.agent.upper()}")
        print(f"Dataset:  {args.dataset}")
        print(f"Model:    {args.model} ({args.provider})")
        print(f"Output:   {args.out}")
        print("=" * 60)

        harness = BenchmarkHarness(
            agent_config=args.agent,
            model=args.model,
            provider=args.provider,
            use_mock=args.mock,
            out_dir=out_dir,
        )

        records = asyncio.run(harness.run_benchmark(dataset_path=args.dataset, limit=args.limit))

        solved = sum(1 for r in records if r.evaluation.resolved)
        print("\n" + "=" * 60)
        print(f"Benchmark Run Completed: {solved}/{len(records)} tasks solved ({round(solved / len(records) * 100 if records else 0, 1)}%)")
        print(f"Raw results saved to: {out_dir}")
        print("=" * 60)

    elif args.subcommand == "report":
        print(f"Generating benchmark report from: {args.results} -> {args.out}")
        out_path = write_report(results_dir=args.results, out_file=args.out)
        print(f"Report successfully generated at: {out_path}")


if __name__ == "__main__":
    main()
