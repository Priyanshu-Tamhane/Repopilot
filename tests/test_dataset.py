"""RepoPilot Tests - Dataset Schema & Pilot Task Verification."""
from __future__ import annotations

from pathlib import Path
from dataset.schema import load_tasks_jsonl, save_tasks_jsonl, BenchmarkTask


def test_dataset_jsonl_load_and_shape():
    """Verify that dataset/tasks.jsonl contains the 3 verified pilot tasks."""
    dataset_path = Path("dataset/tasks.jsonl")
    assert dataset_path.exists(), "dataset/tasks.jsonl must exist"

    tasks = load_tasks_jsonl(dataset_path)
    assert len(tasks) == 3, f"Expected 3 pilot tasks, got {len(tasks)}"

    task_ids = {t.task_id for t in tasks}
    assert "tinydb-635" in task_ids
    assert "tinydb-641" in task_ids
    assert "more-itertools-1309" in task_ids

    for t in tasks:
        assert t.repository.startswith("http")
        assert len(t.base_commit) == 40
        assert len(t.fixed_commit) == 40
        assert t.test_patch.strip()
        assert t.reference_patch.strip()
        assert t.test_command.startswith("pytest")
        assert len(t.fail_to_pass) > 0


def test_dataset_roundtrip(tmp_path: Path):
    """Verify roundtrip serialization of BenchmarkTask."""
    tasks = load_tasks_jsonl("dataset/tasks.jsonl")
    out_file = tmp_path / "test_tasks.jsonl"
    save_tasks_jsonl(tasks, out_file)

    reloaded = load_tasks_jsonl(out_file)
    assert len(reloaded) == len(tasks)
    assert reloaded[0].task_id == tasks[0].task_id
    assert reloaded[0].reference_patch == tasks[0].reference_patch
