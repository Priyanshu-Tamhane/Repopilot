"""RepoPilot Tests - Sandbox Security & Evaluation Integrity (Phase 3).

Validates:
1. Anti-Tampering Gate: Rejects patches that modify test files.
2. Path Traversal Defense: Blocks directory escape attempts (e.g. ../../).
3. Timeout Monitor: Terminates infinite runaway loops within budget.
4. Output Bounding: Caps oversized stdout/stderr at 50,000 chars.
5. Clean-Room Evaluator: Evaluates candidate patch against external authoritative test.
"""
from __future__ import annotations

from pathlib import Path
import pytest

from dataset.schema import load_tasks_jsonl
from execution.docker.sandbox import (
    MAX_OUTPUT_CHARS,
    check_test_tampering,
    validate_safe_path,
    _run_tests_local,
)
from execution.docker.evaluator import CleanRoomEvaluator


def test_tamper_detection_gate():
    """Verify that any patch touching test files is flagged as tampering."""
    # Safe patch (modifies only source code)
    safe_patch = """diff --git a/tinydb/utils.py b/tinydb/utils.py
--- a/tinydb/utils.py
+++ b/tinydb/utils.py
@@ -10,1 +10,1 @@
-    return None
+    return cast(V, value)
"""
    is_tampered, tampered = check_test_tampering(safe_patch)
    assert not is_tampered
    assert len(tampered) == 0

    # Malicious patch 1: Modifies test file directly
    tampered_patch = """diff --git a/tests/test_utils.py b/tests/test_utils.py
--- a/tests/test_utils.py
+++ b/tests/test_utils.py
@@ -50,3 +50,1 @@
-    assert cache["missing"] == "default"
+    assert True
"""
    is_tampered, tampered = check_test_tampering(tampered_patch)
    assert is_tampered
    assert any("test_utils.py" in f for f in tampered)

    # Malicious patch 2: Deletes or touches a test file in tests/ directory
    tampered_patch2 = """--- a/tests/test_queries.py
+++ b/tests/test_queries.py
@@ -1,5 +0,0 @@
-def test_query(): pass
"""
    is_tampered2, tampered2 = check_test_tampering(tampered_patch2)
    assert is_tampered2


def test_path_traversal_defense(tmp_path: Path):
    """Verify that path traversal outside sandbox is detected and blocked."""
    sandbox_dir = tmp_path / "sandbox"
    sandbox_dir.mkdir()

    # Valid internal path
    safe_file = validate_safe_path(sandbox_dir, "src/core.py")
    assert sandbox_dir in safe_file.parents

    # Malicious path escape (relative ../)
    with pytest.raises(PermissionError, match="Path escape attempt detected"):
        validate_safe_path(sandbox_dir, "../../secret_keys.txt")

    # Malicious path escape (absolute root)
    with pytest.raises(PermissionError, match="Path escape attempt detected"):
        validate_safe_path(sandbox_dir, Path.home() / ".ssh" / "id_rsa")


def test_timeout_runaway_loop(tmp_path: Path):
    """Verify that an infinite loop is terminated by the sandbox timeout."""
    test_repo = tmp_path / "infinite_repo"
    test_repo.mkdir()

    (test_repo / "test_loop.py").write_text(
        "import time\n"
        "def test_hang():\n"
        "    while True:\n"
        "        time.sleep(0.1)\n",
        encoding="utf-8",
    )

    # Run with a short 2-second timeout
    passed, failed, output = _run_tests_local(test_repo, timeout_s=2)
    assert passed == 0
    assert failed >= 1
    assert "timed out after 2s" in output


def test_output_bounding(tmp_path: Path):
    """Verify that oversized stdout/stderr is capped at MAX_OUTPUT_CHARS."""
    test_repo = tmp_path / "noisy_repo"
    test_repo.mkdir()

    # Generates ~250,000 characters of spam. When assert False fails, pytest dumps stdout
    (test_repo / "test_spam.py").write_text(
        "def test_noisy():\n"
        "    for _ in range(5000):\n"
        "        print('SPAM_SPAM_SPAM_SPAM_SPAM_SPAM_SPAM_SPAM_SPAM_SPAM')\n"
        "    assert False\n",
        encoding="utf-8",
    )

    _, _, output = _run_tests_local(test_repo, timeout_s=10)
    assert len(output) <= MAX_OUTPUT_CHARS + 200
    assert "[OUTPUT TRUNCATED BY SANDBOX MONITOR]" in output


def test_clean_room_evaluator_tampering_rejection():
    """Verify CleanRoomEvaluator rejects candidate patches that touch tests."""
    tasks = load_tasks_jsonl("dataset/tasks.jsonl")
    assert len(tasks) > 0
    task = tasks[0]

    evaluator = CleanRoomEvaluator()

    # Fake candidate patch that deletes a test file
    fake_tampered_patch = """diff --git a/tests/test_utils.py b/tests/test_utils.py
--- a/tests/test_utils.py
+++ b/tests/test_utils.py
@@ -1,2 +1,1 @@
-# delete test
"""
    result = evaluator.evaluate_candidate(task, fake_tampered_patch)
    assert not result.success
    assert result.failure_category == "test_tampering"
    assert "TAMPERING_DETECTED" in result.error
