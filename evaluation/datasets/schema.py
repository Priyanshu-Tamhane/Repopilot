from __future__ import annotations

from pydantic import BaseModel, Field


class BenchmarkTask(BaseModel):
    """One benchmark task (Spec §14).

    Stores everything needed to reproduce the task: buggy repo files,
    the issue text, the test suite, and ground truth (fail_to_pass).
    Repos are materialized to temp dirs at runtime via seed.materialize().
    """

    id: str = Field(..., description="Stable id, e.g. T01")
    category: str = Field(..., description="Bug category, e.g. add_negatives")
    issue: str = Field(..., description="Issue text fed to the agent")
    files: dict[str, str] = Field(..., description="rel path -> buggy file content")
    tests: dict[str, str] = Field(..., description="rel path -> pytest file content")
    expected_behavior: str = Field(..., description="Human-readable ground truth")
    fail_to_pass: list[str] = Field(..., description="Test fn names failing pre-fix, passing post-fix")
    difficulty: str = "easy"


class BenchmarkDataset(BaseModel):
    name: str
    version: str
    tasks: list[BenchmarkTask]

    def ids(self) -> list[str]:
        return [t.id for t in self.tasks]

    def get(self, task_id: str) -> BenchmarkTask:
        
        for t in self.tasks:
            if t.id == task_id:
                return t
        raise KeyError(f"unknown task {task_id}")
