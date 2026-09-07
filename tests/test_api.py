from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "sandbox_mode" in data


def test_root():
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["name"] == "RepoPilot"


def _make_dummy_repo(tmp: Path) -> Path:
    repo = tmp / "dummy_repo"
    repo.mkdir()
    # git init
    import subprocess

    subprocess.run(["git", "init"], cwd=str(repo), capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(repo), capture_output=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=str(repo), capture_output=True)

    (repo / "calculator.py").write_text(
        """
def add(a, b):
    # BUG: incorrect handling of negatives
    if b < 0:
        return a - b
    return a + b

def subtract(a, b):
    return a - b
""",
        encoding="utf-8",
    )
    (repo / "test_calculator.py").write_text(
        """
from calculator import add

def test_add_positive():
    assert add(2, 3) == 5

def test_add_negative():
    assert add(2, -3) == -1

def test_add_both_negative():
    assert add(-2, -3) == -5
""",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=str(repo), capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=str(repo), capture_output=True)
    return repo


def test_post_tasks_local_repo():
    with tempfile.TemporaryDirectory() as td:
        repo = _make_dummy_repo(Path(td))
        payload = {
            "repository": str(repo),
            "issue": "Fix add() in calculator.py: it returns wrong value for negative numbers (e.g., add(2, -3) should be -1 but currently returns 5)",
        }
        resp = client.post("/tasks", json=payload)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        # Spec §2 output shape
        assert "success" in data
        assert "patch" in data
        assert "tests_passed" in data
        assert "tests_failed" in data
        assert "duration_seconds" in data
        assert "input_tokens" in data
        assert "output_tokens" in data
        assert "llm_calls" in data
        assert "tool_calls" in data
        assert "estimated_cost" in data
        # Should succeed with mock heuristic fix
        assert data["tests_failed"] == 0
        assert data["success"] is True
        assert data["patch"] != ""
        assert data["llm_calls"] >= 1
