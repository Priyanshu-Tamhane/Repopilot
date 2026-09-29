import asyncio
import tempfile
from pathlib import Path

import pytest

from agents.coordinator import MultiAgentCoordinator
from agents.baseline.agent import BaselineAgent
from inference.router.router import ModelRouter, ModelTier, RoutingDecision


def _create_test_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "calculator.py").write_text(
        "def add(a, b):\n    # bug\n    if b < 0:\n        return a - b\n    return a + b\n",
        encoding="utf-8",
    )
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


def test_complexity_scoring():
    router = ModelRouter()

    # Easy keyword issue
    easy_score, easy_reasons = router.calculate_complexity(
        issue="Fix typo in docstring and add negative test check",
        context="def add(a, b): return a + b",
        candidate_files=["calculator.py"],
    )
    assert easy_score < 0.50
    assert any("easy" in r for r in easy_reasons)

    # Hard keyword issue
    hard_score, hard_reasons = router.calculate_complexity(
        issue="Fix race condition deadlock in asyncio recursion memory leak",
        context="x" * 5000,
        candidate_files=["file1.py", "file2.py", "file3.py"],
    )
    assert hard_score >= 0.50
    assert any("hard" in r for r in hard_reasons)


def test_route_and_escalate():
    router = ModelRouter(
        cheap_model="openai/gpt-oss-20b",
        heavy_model="openai/gpt-oss-120b",
    )

    # Easy issue -> CHEAP tier
    decision_cheap = router.route("Fix addition sign bug")
    assert decision_cheap.tier == ModelTier.CHEAP
    assert decision_cheap.model_name == "openai/gpt-oss-20b"
    assert decision_cheap.escalated is False

    # Hard issue -> HEAVY tier
    decision_heavy = router.route("Fix complex recursive deadlock algorithm optimization")
    assert decision_heavy.tier == ModelTier.HEAVY
    assert decision_heavy.model_name == "openai/gpt-oss-120b"

    # Cascade escalation
    escalated = router.escalate(decision_cheap, failure_reason="AssertionError: 5 != 6")
    assert escalated.tier == ModelTier.HEAVY
    assert escalated.model_name == "openai/gpt-oss-120b"
    assert escalated.escalated is True
    assert "Escalated" in escalated.reason

    # Already heavy should not change
    no_op = router.escalate(decision_heavy)
    assert no_op.model_name == "openai/gpt-oss-120b"
    assert no_op.escalated is False


def test_mock_router():
    router = ModelRouter(use_mock=True)
    assert router.cheap_model == "mock-gpt-4o-mini-cheap"
    assert router.heavy_model == "mock-gpt-4o-mini"

    decision = router.route("Fix typo in function")
    assert decision.tier == ModelTier.CHEAP
    assert decision.model_name == "mock-gpt-4o-mini-cheap"


@pytest.mark.asyncio
async def test_coordinator_with_routing():
    with tempfile.TemporaryDirectory() as td:
        repo_path = _create_test_repo(Path(td))
        issue = "Fix add() in calculator.py: returns wrong value for negative numbers"

        coordinator = MultiAgentCoordinator(
            workdir=td,
            sandbox_mode="local",
            use_mock=True,
            model_routing=True,
        )

        response = await coordinator.run(str(repo_path), issue)
        assert response.success is True
        assert response.tests_passed == 2
        assert response.tests_failed == 0
        assert response.estimated_cost > 0.0

        trace = response.trace
        assert "routing" in trace
        assert trace["routing"]["initial_tier"] in ("cheap", "heavy")
        assert "mock-gpt-4o-mini" in trace["routing"]["model_name"]


@pytest.mark.asyncio
async def test_baseline_agent_with_routing():
    with tempfile.TemporaryDirectory() as td:
        repo_path = _create_test_repo(Path(td))
        issue = "Fix add() in calculator.py: returns wrong value for negative numbers"

        agent = BaselineAgent(
            workdir=td,
            sandbox_mode="local",
            use_mock=True,
            model_routing=True,
        )

        response = await agent.run(str(repo_path), issue)
        assert response.success is True
        assert "routing" in response.trace
        assert response.trace["routing"]["tier"] in ("cheap", "heavy")
