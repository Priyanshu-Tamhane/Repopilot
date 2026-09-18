"""Phase 2 benchmark tests: dataset validity, metrics math, mini runner."""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from agents.baseline.agent import BaselineAgent
from api.schemas.tasks import TaskResponse
from evaluation.datasets.seed import build_dataset, load_json, materialize
from evaluation.metrics.collector import aggregate
from evaluation.runner.runner import BenchmarkRunner


def test_dataset_shape():
    ds = build_dataset()
    assert ds.name == "repopilot-seed"
    assert len(ds.tasks) == 20
    assert len({t.id for t in ds.tasks}) == 20
    for t in ds.tasks:
        assert t.issue and t.files and t.tests and t.expected_behavior
        assert t.fail_to_pass, f"{t.id} needs fail_to_pass ground truth"
        combined_tests = "\n".join(t.tests.values())
        for fn in t.fail_to_pass:
            assert fn in combined_tests, f"{t.id}: {fn} missing from tests"


def test_dataset_json_roundtrip():
    ds = load_json("evaluation/datasets/seed_tasks.json")
    assert len(ds.tasks) == 20
    assert ds.ids()[0] == "T01"


def test_seed_bugs_fail_prefix():
    """Every seed repo must FAIL pytest before the fix (bugs are real)."""
    ds = build_dataset()
    with tempfile.TemporaryDirectory(prefix="bench-valid-") as td:
        for task in ds.tasks:
            repo = materialize(task, Path(td))
            r = subprocess.run(
                ["python", "-m", "pytest", "-q"],
                cwd=str(repo), capture_output=True, text=True, timeout=120,
            )
            assert r.returncode != 0, f"{task.id} unexpectedly passes pre-fix"


def test_metrics_math():
    def resp(success, passed, failed, dur, tok, cost, llm=1, tool=5):
        return TaskResponse(
            success=success, patch="diff" if success else "", tests_passed=passed,
            tests_failed=failed, duration_seconds=dur, input_tokens=tok,
            output_tokens=tok // 2, llm_calls=llm, tool_calls=tool, estimated_cost=cost,
        )

    results = [
        resp(True, 2, 0, 1.0, 100, 0.01),
        resp(True, 3, 0, 2.0, 200, 0.02),
        resp(False, 0, 2, 3.0, 300, 0.03),
        resp(True, 1, 0, 4.0, 400, 0.04),
    ]
    m = aggregate(results, wall_seconds=120.0)
    assert m.total == 4 and m.successes == 3
    assert m.success_rate == 0.75
    assert m.test_pass_rate == 6 / 8
    assert m.patch_rate == 0.75
    assert m.avg_latency == 2.5
    assert m.median_latency == 2.5
    assert m.p95_latency == 4.0
    assert m.total_tokens == 1500
    assert m.total_llm_calls == 4
    assert m.cost_per_task == round(0.10 / 4, 4)
    assert m.cost_per_success == round(0.10 / 3, 4)
    assert m.tasks_per_minute == 2.0
    assert aggregate([]).total == 0


async def test_runner_mini_mock():
    """3-task mock run (add_negatives + reverse + factorial) must go 3/3."""
    ds = build_dataset()
    mini_ids = {"T01", "T13", "T18"}
    mini = [t for t in ds.tasks if t.id in mini_ids]
    assert len(mini) == 3

    runner = BenchmarkRunner(
        agent_factory=lambda: BaselineAgent(use_mock=True, sandbox_mode="local"),
        timeout_s=120.0,
    )
    task_ids, results, wall = [], [], 0.0
    import time

    start = time.time()
    with tempfile.TemporaryDirectory(prefix="bench-mini-") as td:
        for task in mini:
            r = await runner.run_task(task, Path(td))
            task_ids.append(task.id)
            results.append(r)
    wall = time.time() - start

    for tid, r in zip(task_ids, results):
        assert r.success, f"{tid} failed: {(r.error or '')[:300]}"
        assert r.llm_calls >= 1 and r.patch.strip()
    m = aggregate(results, wall_seconds=wall)
    assert m.success_rate == 1.0
    assert m.test_pass_rate == 1.0
