import asyncio
import tempfile
from pathlib import Path

import pytest

from agents.debugger import DebuggerAgent
from agents.implementer import ImplementerAgent
from agents.planner import PlannerAgent
from agents.protocol import SharedTaskState
from agents.researcher import ResearcherAgent
from agents.reviewer import ReviewerAgent
from agents.tester import TesterAgent
from inference.models.mock import MockLLMProvider


def _create_buggy_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    # Buggy calculator
    (repo / "calculator.py").write_text(
        "def add(a, b):\n    # bug\n    if b < 0:\n        return a - b\n    return a + b\n",
        encoding="utf-8",
    )
    # Pytest file
    (repo / "test_calculator.py").write_text(
        "from calculator import add\n\n"
        "def test_add_positive():\n    assert add(2, 3) == 5\n\n"
        "def test_add_negative():\n    assert add(2, -3) == -1\n",
        encoding="utf-8",
    )
    import subprocess

    subprocess.run(["git", "init"], cwd=str(repo), capture_output=True)
    subprocess.run(["git", "add", "."], cwd=str(repo), capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=str(repo), capture_output=True)
    return repo


@pytest.mark.asyncio
async def test_multi_agent_components():
    with tempfile.TemporaryDirectory() as td:
        repo_path = _create_buggy_repo(Path(td))
        issue = "Fix add() in calculator.py: returns wrong value for negative numbers like add(2, -3)"

        mock_provider = MockLLMProvider()
        state = SharedTaskState(
            repository=str(repo_path),
            issue=issue,
            repo_path=repo_path,
            sandbox_mode="local",
            use_mock=True,
        )

        # 1. Planner
        planner = PlannerAgent(mock_provider)
        plan = await planner.run(state)
        assert "category" in plan
        assert "steps" in plan
        assert state.plan["category"] == "add_negatives"

        # 2. Researcher
        researcher = ResearcherAgent(mock_provider)
        research_summary = await researcher.run(state)
        assert "calculator.py" in state.candidate_files
        assert len(state.research_context) > 0

        # 3. Implementer
        implementer = ImplementerAgent(mock_provider)
        edits = await implementer.run(state)
        assert len(edits) > 0
        assert "calculator.py" in edits[0]

        # 4. Tester
        tester = TesterAgent(sandbox_mode="local")
        test_res = await tester.run(state)
        assert test_res["all_passed"] is True
        assert state.test_passed == 2
        assert state.test_failed == 0

        # 5. Debugger (test diagnosis capability)
        debugger = DebuggerAgent(mock_provider)
        state.test_output = "FAILED test_calculator.py::test_add_negative - AssertionError: assert 5 == -1"
        hint = await debugger.run(state)
        assert len(hint) > 0

        # 6. Reviewer
        reviewer = ReviewerAgent(mock_provider)
        review = await reviewer.run(state)
        assert review["approved"] is True
        assert "diff --git" in state.patch
        # Invariant check: test files must not be modified
        assert "test_calculator.py" not in state.patch
