"""RepoPilot Dataset - Task Schema & Serialization.

Defines the canonical benchmark task schema matching Phase 1 architecture spec.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List


@dataclass
class EnvironmentSpec:
    python_version: str = "3.11"
    install_command: str = "pip install -e ."
    dependencies: List[str] = field(default_factory=list)


@dataclass
class BenchmarkTask:
    task_id: str
    repository: str  # GitHub clone URL
    repo_name: str   # e.g. "pallets/click"
    base_commit: str # Buggy parent commit SHA
    fixed_commit: str # Merged commit SHA
    issue_url: str
    issue_title: str
    issue_description: str
    test_patch: str  # Test changes diff that reproduce the bug
    reference_patch: str # Fix diff (source files only, no tests)
    test_command: str # e.g. "pytest tests/test_unicode.py -k test_flags"
    fail_to_pass: List[str] # List of test names expected to fail on base and pass after fix
    pass_to_pass: List[str] = field(default_factory=list) # Existing tests that must not regress
    environment: Dict[str, Any] = field(default_factory=lambda: asdict(EnvironmentSpec()))
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> BenchmarkTask:
        return cls(**data)


def save_tasks_jsonl(tasks: List[BenchmarkTask], path: Path | str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        for t in tasks:
            f.write(json.dumps(t.to_dict()) + "\n")


def load_tasks_jsonl(path: Path | str) -> List[BenchmarkTask]:
    p = Path(path)
    if not p.exists():
        return []
    tasks = []
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                tasks.append(BenchmarkTask.from_dict(json.loads(line)))
    return tasks
