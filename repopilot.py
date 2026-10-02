"""RepoPilot - Unified CLI Command Center.

One entry point for the entire project:
  1. run       - Run RepoPilot on any repository and issue
  2. demo      - Run an instant end-to-end demo (easy/hard bug, mock or real Groq LLM)
  3. benchmark - Run evaluation experiments (Exp 1 Baseline, Exp 2 RAG, Exp 3 Multi-Agent, Exp 4 Routing)
  4. compare   - Compare benchmark metrics and cost savings
  5. serve     - Launch the FastAPI server
  6. test      - Run unit tests with pytest
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import tempfile
from pathlib import Path


# ---------------------------------------------------------------------------
# Demo Helper
# ---------------------------------------------------------------------------
def _create_demo_repo(tmp_path: Path, task_type: str = "easy") -> Path:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)

    if task_type == "easy":
        (repo / "calculator.py").write_text(
            "def add(a, b):\n"
            "    # bug: subtraction instead of addition for negatives\n"
            "    if b < 0:\n"
            "        return a - b\n"
            "    return a + b\n",
            encoding="utf-8",
        )
        (repo / "test_calculator.py").write_text(
            "from calculator import add\n\n"
            "def test_add_positive():\n    assert add(2, 3) == 5\n\n"
            "def test_add_negative():\n    assert add(2, -3) == -1\n",
            encoding="utf-8",
        )
    else:
        (repo / "concurrency_queue.py").write_text(
            "def process_items(items):\n"
            "    # bug: off-by-one in complex algorithm\n"
            "    results = []\n"
            "    for i in range(len(items) - 1):\n"
            "        results.append(items[i] * 2)\n"
            "    return results\n",
            encoding="utf-8",
        )
        (repo / "test_concurrency_queue.py").write_text(
            "from concurrency_queue import process_items\n\n"
            "def test_all_items_processed():\n"
            "    assert process_items([1, 2, 3]) == [2, 4, 6]\n",
            encoding="utf-8",
        )

    import subprocess
    subprocess.run(["git", "init"], cwd=str(repo), capture_output=True)
    subprocess.run(["git", "add", "."], cwd=str(repo), capture_output=True)
    subprocess.run(["git", "commit", "-m", "init demo repo"], cwd=str(repo), capture_output=True)
    return repo


# ---------------------------------------------------------------------------
# Command Handlers
# ---------------------------------------------------------------------------
async def handle_run(args: argparse.Namespace) -> None:
    from api.dependencies.config import get_settings
    settings = get_settings()

    use_mock = True if args.mock else (False if args.real else settings.llm_mock)
    phase = getattr(args, "phase", 5)

    print("=" * 65)
    print(f" RepoPilot Execution | Phase {phase} | Mode: {'MOCK (Offline)' if use_mock else 'REAL LLM (Groq)'}")
    print(f" Repository: {args.repo}")
    print(f" Issue     : {args.issue}")
    print("=" * 65)

    if phase == 1:
        from agents.baseline.agent import BaselineAgent
        agent = BaselineAgent(
            sandbox_mode=args.sandbox,
            use_mock=use_mock,
            model=settings.groq_model,
            api_key=settings.groq_api_key if not use_mock else "",
            provider="groq" if not use_mock else "mock",
            use_retrieval=False,
            model_routing=False,
        )
    elif phase == 3:
        from agents.baseline.agent import BaselineAgent
        agent = BaselineAgent(
            sandbox_mode=args.sandbox,
            use_mock=use_mock,
            model=settings.groq_model,
            api_key=settings.groq_api_key if not use_mock else "",
            provider="groq" if not use_mock else "mock",
            use_retrieval=True,
            model_routing=False,
        )
    elif phase == 4:
        from agents.coordinator import MultiAgentCoordinator
        agent = MultiAgentCoordinator(
            sandbox_mode=args.sandbox,
            use_mock=use_mock,
            model=settings.groq_model,
            api_key=settings.groq_api_key if not use_mock else "",
            provider="groq" if not use_mock else "mock",
            model_routing=False,
            max_retries=args.retries,
        )
    else:  # Phase 5 (Default: Multi-Agent + Dynamic Model Routing)
        from agents.coordinator import MultiAgentCoordinator
        agent = MultiAgentCoordinator(
            sandbox_mode=args.sandbox,
            use_mock=use_mock,
            model=settings.groq_model,
            api_key=settings.groq_api_key if not use_mock else "",
            provider="groq" if not use_mock else "mock",
            model_routing=True,
            cheap_model=settings.groq_cheap_model if not use_mock else "mock-gpt-4o-mini-cheap",
            heavy_model=settings.groq_model if not use_mock else "mock-gpt-4o-mini",
            max_retries=args.retries,
        )

    result = await agent.run(args.repo, args.issue)

    print("\n" + "=" * 65)
    print(" TASK RESULT")
    print("=" * 65)
    print(f" Success        : {result.success}")
    print(f" Tests Passed   : {result.tests_passed}")
    print(f" Tests Failed   : {result.tests_failed}")
    print(f" Latency        : {result.duration_seconds}s")
    print(f" Estimated Cost : ${result.estimated_cost:.5f}")

    routing = result.trace.get("routing") if result.trace else None
    if routing:
        print("\n--- MODEL ROUTING ---")
        print(f" Assigned Model : {routing.get('model_name') or routing.get('model')} (Tier: {routing.get('final_tier', routing.get('tier', '')).upper()})")
        print(f" Complexity     : {routing.get('complexity_score', routing.get('score'))}")
        print(f" Reason         : {routing.get('reason')}")

    if result.patch.strip():
        print("\n--- GENERATED PATCH ---")
        print(result.patch.strip()[:600])


def handle_demo(args: argparse.Namespace) -> None:
    with tempfile.TemporaryDirectory() as td:
        repo_dir = _create_demo_repo(Path(td), task_type=args.task)
        if args.task == "easy":
            args.issue = "Fix add() in calculator.py: returns wrong value for negative numbers like add(2, -3)"
        else:
            args.issue = "Fix deadlock and concurrency race condition in process_items recursion algorithm"
        args.repo = str(repo_dir)
        args.sandbox = "local"
        args.retries = 3
        asyncio.run(handle_run(args))


def handle_benchmark(args: argparse.Namespace) -> None:
    if args.mock:
        os.environ["LLM_MOCK"] = "true"
    elif args.real:
        os.environ["LLM_MOCK"] = "false"

    cli_args = ["cli.py", "--sandbox", args.sandbox]
    if args.limit:
        cli_args.extend(["--limit", str(args.limit)])

    exp = getattr(args, "exp", 4)
    if exp == 1:
        cli_args.extend(["--experiment", "exp1_baseline"])
    elif exp == 2:
        cli_args.extend(["--retrieval", "--experiment", "exp2_retrieval"])
    elif exp == 3:
        cli_args.extend(["--multi-agent", "--experiment", "exp3_multi_agent"])
    elif exp == 4:
        cli_args.extend(["--multi-agent", "--model-routing", "--experiment", "exp4_routing"])
    elif exp == 5:
        cli_args.extend(["--multi-agent", "--model-routing", "--cache", "--experiment", "exp5_caching"])
    elif exp == 6:
        workers = args.workers if args.workers > 1 else 4
        cli_args.extend(["--multi-agent", "--model-routing", "--workers", str(workers), "--experiment", f"exp6_scaling_w{workers}"])
    else:
        cli_args.extend(["--multi-agent", "--model-routing", "--experiment", "exp4_routing"])

    if args.cache and "--cache" not in cli_args:
        cli_args.append("--cache")
    if args.workers > 1 and "--workers" not in cli_args:
        cli_args.extend(["--workers", str(args.workers)])

    from evaluation.runner.cli import main as runner_main
    sys.argv = cli_args
    runner_main()


def handle_compare(args: argparse.Namespace) -> None:
    import glob
    results_dir = Path("evaluation/results")

    if args.file1 and args.file2:
        f1, f2 = args.file1, args.file2
    else:
        # Auto-pick latest Exp3/4/5/6 results
        all_results = sorted(results_dir.glob("exp*.json"))
        if len(all_results) < 2:
            print("Need at least two benchmark result JSON files to compare.")
            return
        f1 = str(all_results[-2])
        f2 = str(all_results[-1])

    from evaluation.experiments.compare import main as compare_main
    sys.argv = ["compare.py", f1, f2]
    compare_main()


def handle_serve(args: argparse.Namespace) -> None:
    import uvicorn
    print(f"Starting RepoPilot API server on {args.host}:{args.port}...")
    uvicorn.run("api.main:app", host=args.host, port=args.port, reload=args.reload)


def handle_test(args: argparse.Namespace) -> None:
    import pytest
    pytest_args = ["-v"] if args.verbose else []
    if args.target:
        pytest_args.append(args.target)
    sys.exit(pytest.main(pytest_args))


# ---------------------------------------------------------------------------
# CLI Argument Parser
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        prog="repopilot",
        description="RepoPilot: Evaluation-Driven Coding-Agent Infrastructure",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # 1. run
    p_run = subparsers.add_parser("run", help="Run RepoPilot on a repository and issue")
    p_run.add_argument("--repo", required=True, help="Repository path or GitHub URL")
    p_run.add_argument("--issue", required=True, help="Issue description")
    p_run.add_argument("--phase", type=int, choices=[1, 3, 4, 5, 6], default=5, help="Agent architecture phase (default: 5)")
    p_run.add_argument("--mock", action="store_true", help="Use offline mock LLM ($0.00 cost)")
    p_run.add_argument("--real", action="store_true", help="Use real Groq LLM from .env")
    p_run.add_argument("--cache", action="store_true", help="Enable prompt & response caching (Phase 6)")
    p_run.add_argument("--sandbox", choices=["auto", "local", "docker"], default="auto", help="Sandbox execution mode")
    p_run.add_argument("--retries", type=int, default=3, help="Max repair retries")

    # 2. demo
    p_demo = subparsers.add_parser("demo", help="Run an instant demo on a built-in test case")
    p_demo.add_argument("--task", choices=["easy", "hard"], default="easy", help="Bug type: easy (routes to cheap) or hard (routes to heavy)")
    p_demo.add_argument("--phase", type=int, choices=[1, 3, 4, 5, 6], default=5, help="Agent architecture phase (default: 5)")
    p_demo.add_argument("--mock", action="store_true", help="Use offline mock LLM ($0.00 cost)")
    p_demo.add_argument("--real", action="store_true", help="Use real Groq LLM from .env")
    p_demo.add_argument("--cache", action="store_true", help="Enable prompt & response caching (Phase 6)")

    # 3. benchmark
    p_bm = subparsers.add_parser("benchmark", help="Run evaluation benchmark suite")
    p_bm.add_argument("--exp", type=int, choices=[1, 2, 3, 4, 5, 6], default=4, help="Experiment: 1=Baseline, 2=RAG, 3=Multi-Agent, 4=Routing, 5=Caching, 6=Worker Scaling (default: 4)")
    p_bm.add_argument("--limit", type=int, default=None, help="Limit number of tasks (e.g. --limit 3)")
    p_bm.add_argument("--mock", action="store_true", help="Run benchmark with mock LLM")
    p_bm.add_argument("--real", action="store_true", help="Run benchmark with real Groq LLM")
    p_bm.add_argument("--cache", action="store_true", help="Enable Phase 6 prompt caching (Exp 5)")
    p_bm.add_argument("--workers", type=int, default=1, help="Parallel worker concurrency: 1, 2, 4, 8 (Exp 6)")
    p_bm.add_argument("--sandbox", choices=["auto", "local", "docker"], default="local", help="Sandbox mode")

    # 4. compare
    p_comp = subparsers.add_parser("compare", help="Compare two benchmark runs (or auto-compare latest)")
    p_comp.add_argument("file1", nargs="?", help="Baseline benchmark JSON file")
    p_comp.add_argument("file2", nargs="?", help="Candidate benchmark JSON file")

    # 5. serve
    p_serve = subparsers.add_parser("serve", help="Start the FastAPI server")
    p_serve.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    p_serve.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000)")
    p_serve.add_argument("--reload", action="store_true", help="Enable auto-reload")

    # 6. test
    p_test = subparsers.add_parser("test", help="Run project test suite with pytest")
    p_test.add_argument("--verbose", "-v", action="store_true", default=True, help="Verbose pytest output")
    p_test.add_argument("--target", help="Specific test file or test expression")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "run":
        asyncio.run(handle_run(args))
    elif args.command == "demo":
        handle_demo(args)
    elif args.command == "benchmark":
        handle_benchmark(args)
    elif args.command == "compare":
        handle_compare(args)
    elif args.command == "serve":
        handle_serve(args)
    elif args.command == "test":
        handle_test(args)


if __name__ == "__main__":
    main()
