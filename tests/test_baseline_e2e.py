"""E2E baseline test that mimics solving one issue (Phase 1 success criteria)."""
import tempfile
from pathlib import Path

import pytest
import subprocess

from agents.baseline.agent import BaselineAgent


def _make_repo(tmp: Path) -> Path:
    repo = tmp / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=str(repo), capture_output=True)
    subprocess.run(["git", "config", "user.email", "a@a.com"], cwd=str(repo), capture_output=True)
    subprocess.run(["git", "config", "user.name", "a"], cwd=str(repo), capture_output=True)
    (repo / "calculator.py").write_text("def add(a, b):\n    if b < 0:\n        return a - b\n    return a + b\n", encoding="utf-8")
    (repo / "test_calc.py").write_text(
        "from calculator import add\ndef test_neg():\n    assert add(2, -3) == -1\ndef test_pos():\n    assert add(2, 3) == 5\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=str(repo), capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=str(repo), capture_output=True)
    return repo


@pytest.mark.asyncio
async def test_baseline_solves_one_issue():
    with tempfile.TemporaryDirectory() as td:
        repo = _make_repo(Path(td))
        agent = BaselineAgent(use_mock=True, sandbox_mode="local")
        result = await agent.run(str(repo), "Fix add() bug with negative numbers")
        assert result.llm_calls == 1
        assert result.tool_calls >= 3
        assert result.duration_seconds > 0
        assert result.input_tokens > 0
        assert result.output_tokens > 0
        # Patch should be non-empty and tests should pass
        assert result.patch != ""
        assert result.tests_failed == 0
        assert result.success is True
        assert result.trace is not None
