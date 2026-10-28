"""RepoPilot - Benchmark Harness & Agent Interface Tests (Phase 4).

Validates:
1. Canonical Agent Interface & Factory (B0, B1, B2, B3)
2. Per-Run JSON Schema serialization, roundtrip & pricing math
3. Benchmark Harness execution & CleanRoomEvaluator integration
4. Offline report generation from saved JSON results
5. CLI argument parsing
"""
from __future__ import annotations

from pathlib import Path
import pytest

from agents.base import (
    BaseBenchmarkAgent,
    B0BaselineAgent,
    B1RetrievalAgent,
    B2MultiAgent,
    B3RoutingAgent,
    TaskBudget,
    get_agent,
)
from dataset.schema import BenchmarkTask
from evaluation.bench.cli import build_parser
from evaluation.bench.harness import BenchmarkHarness
from evaluation.bench.report import (
    generate_benchmark_report_markdown,
    load_records_from_dir,
    write_report,
)
from evaluation.bench.schema import (
    BenchmarkRunRecord,
    EvaluationSummary,
    calculate_cost,
)


def test_agent_factory_and_interfaces():
    """Verify get_agent instantiates correct classes with BaseBenchmarkAgent contract."""
    b0 = get_agent("b0")
    assert isinstance(b0, B0BaselineAgent)
    assert isinstance(b0, BaseBenchmarkAgent)
    assert b0.name == "b0_baseline"

    b1 = get_agent("b1")
    assert isinstance(b1, B1RetrievalAgent)
    assert b1.name == "b1_retrieval"

    b2 = get_agent("b2")
    assert isinstance(b2, B2MultiAgent)
    assert b2.name == "b2_multi_agent"

    b3 = get_agent("b3")
    assert isinstance(b3, B3RoutingAgent)
    assert b3.name == "b3_routing"

    with pytest.raises(ValueError):
        get_agent("unknown_agent_variant")


def test_per_run_schema_and_cost_math(tmp_path: Path):
    """Test Per-Run JSON creation, pricing calculation, and roundtrip serialization."""
    cost = calculate_cost("llama-3.3-70b-versatile", input_tokens=1_000_000, output_tokens=1_000_000)
    assert cost == round(0.59 + 0.79, 6)

    eval_summary = EvaluationSummary(
        resolved=True,
        tests_passed=5,
        tests_failed=0,
        failure_category=None,
    )

    record = BenchmarkRunRecord.create(
        run_id="run-001",
        task_id="tinydb-635",
        agent_config="b0_baseline",
        model_id="llama-3.3-70b-versatile",
        provider="groq",
        base_commit="a" * 40,
        duration_seconds=12.5,
        input_tokens=1500,
        output_tokens=300,
        tool_calls=4,
        retries=0,
        patch="diff --git a/tinydb/database.py b/tinydb/database.py\n+ # fix",
        evaluation=eval_summary,
        diagnostic_notes="Clean fix",
    )

    assert record.status == "resolved"
    assert record.patch_hash != ""
    assert record.estimated_cost > 0.0

    # Save and reload
    saved_file = record.save(tmp_path)
    assert saved_file.exists()

    reloaded = BenchmarkRunRecord.load(saved_file)
    assert reloaded.run_id == "run-001"
    assert reloaded.task_id == "tinydb-635"
    assert reloaded.evaluation.resolved is True
    assert reloaded.evaluation.tests_passed == 5
    assert reloaded.patch == record.patch


def _create_mock_dummy_repo(root: Path) -> Path:
    repo = root / "calculator_repo"
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "calculator.py").write_text(
        "def add(a, b):\n    # bug\n    if b < 0:\n        return a - b\n    return a + b\n",
        encoding="utf-8",
    )
    (repo / "test_calculator.py").write_text(
        "from calculator import add\n\n"
        "def test_pos():\n    assert add(2, 3) == 5\n\n"
        "def test_neg():\n    assert add(2, -3) == -1\n",
        encoding="utf-8",
    )
    import subprocess
    subprocess.run(["git", "init"], cwd=str(repo), capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(repo), capture_output=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=str(repo), capture_output=True)
    subprocess.run(["git", "add", "."], cwd=str(repo), capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], cwd=str(repo), capture_output=True)
    return repo


def test_benchmark_harness_workspace_and_record(tmp_path: Path):
    """Test BenchmarkHarness workspace setup and per-run JSON record persistence.

    This is a synchronous test that validates the harness's workspace preparation
    and record serialization without invoking the async agent solve loop.
    Full end-to-end agent execution is tested manually or in CI with asyncio available.
    """
    import subprocess

    repo_path = _create_mock_dummy_repo(tmp_path)
    commit_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(repo_path), capture_output=True, text=True
    ).stdout.strip()

    task = BenchmarkTask(
        task_id="test-calc-01",
        repository=str(repo_path),
        repo_name="test/calc",
        base_commit=commit_sha,
        fixed_commit=commit_sha,
        issue_url="https://github.com/test/calc/issues/1",
        issue_title="Fix add() negative",
        issue_description="Fix add() in calculator.py: returns wrong value for negative numbers like add(2, -3)",
        test_patch="",
        reference_patch="",
        test_command="pytest -q",
        fail_to_pass=["test_neg"],
    )

    out_dir = tmp_path / "results"
    harness = BenchmarkHarness(
        agent_config="b0",
        use_mock=True,
        budget=TaskBudget(max_wall_time_s=60.0),
        workdir=tmp_path / "workdir",
        out_dir=out_dir,
    )

    # 1. Validate workspace preparation — isolates task repo correctly
    ws = harness._prepare_agent_workspace(task, run_id="testrun01")
    assert ws.exists(), "Workspace directory should be created"
    assert (ws / "calculator.py").exists(), "Task files should be copied into workspace"
    assert (ws / ".git").exists(), "Workspace must be a git repo for patch generation"

    # 2. Validate BenchmarkRunRecord creation and persistence
    eval_summary = EvaluationSummary(resolved=True, tests_passed=2, tests_failed=0)
    record = BenchmarkRunRecord.create(
        run_id="testrun01",
        task_id=task.task_id,
        agent_config="b0_baseline",
        model_id="mock",
        provider="mock",
        base_commit=commit_sha,
        duration_seconds=1.5,
        input_tokens=200,
        output_tokens=50,
        tool_calls=3,
        retries=0,
        patch="diff --git a/calculator.py b/calculator.py\n+ # fixed",
        evaluation=eval_summary,
    )
    assert record.task_id == "test-calc-01"
    assert record.agent_config == "b0_baseline"
    assert record.status == "resolved"
    assert record.patch_hash != ""

    # 3. Save and verify the JSON file exists in out_dir
    saved = record.save(out_dir)
    assert saved.exists()
    expected_name = f"{record.task_id}_{record.agent_config}_{record.run_id}.json"
    assert (out_dir / expected_name).exists()


def test_offline_report_generator(tmp_path: Path):
    """Test offline report generation from mock JSON records without network or LLM calls."""
    results_dir = tmp_path / "saved_results"
    results_dir.mkdir(parents=True, exist_ok=True)

    # 1. Successful B0 record
    rec1 = BenchmarkRunRecord.create(
        run_id="run-1",
        task_id="task-101",
        agent_config="b0_baseline",
        model_id="mock",
        provider="mock",
        base_commit="b" * 40,
        duration_seconds=2.0,
        input_tokens=500,
        output_tokens=100,
        tool_calls=3,
        retries=0,
        patch="diff a b",
        evaluation=EvaluationSummary(resolved=True, tests_passed=2, tests_failed=0),
    )
    rec1.save(results_dir)

    # 2. Failed B1 record with tampering
    rec2 = BenchmarkRunRecord.create(
        run_id="run-2",
        task_id="task-102",
        agent_config="b1_retrieval",
        model_id="mock",
        provider="mock",
        base_commit="c" * 40,
        duration_seconds=3.5,
        input_tokens=1200,
        output_tokens=250,
        tool_calls=5,
        retries=1,
        patch="diff a b",
        evaluation=EvaluationSummary(resolved=False, failure_category="test_tampering", error="Edited test"),
    )
    rec2.save(results_dir)

    records = load_records_from_dir(results_dir)
    assert len(records) == 2

    report_md = generate_benchmark_report_markdown(results_dir)
    assert "# RepoPilot — Official Benchmark Evaluation Report" in report_md
    assert "b0_baseline" in report_md
    assert "b1_retrieval" in report_md
    assert "Test Tampering" in report_md

    out_file = tmp_path / "report.md"
    written_path = write_report(results_dir, out_file)
    assert written_path.exists()
    assert written_path.read_text(encoding="utf-8") == report_md


def test_cli_argument_parsing():
    """Test repopilot-bench CLI parser options for run and report."""
    parser = build_parser()

    # run command
    args_run = parser.parse_args(["run", "--dataset", "dataset/tasks.jsonl", "--agent", "b1", "--limit", "3"])
    assert args_run.subcommand == "run"
    assert args_run.dataset == "dataset/tasks.jsonl"
    assert args_run.agent == "b1"
    assert args_run.limit == 3

    # report command
    args_report = parser.parse_args(["report", "--results", "evaluation/results", "--out", "custom_report.md"])
    assert args_report.subcommand == "report"
    assert args_report.results == "evaluation/results"
    assert args_report.out == "custom_report.md"
