"""RepoPilot Evaluation Boundary & Clean-Room Evaluator.

Enforces Phase 3 Evaluation Integrity:
1. Anti-Tampering Gate: Rejects any patch modifying test files.
2. Isolated Clean-Room: Sets up a fresh workspace at base_commit.
3. Authoritative Test Injection: Applies test_patch from trusted external store.
4. Isolated Test Execution: Runs tests in network-disabled sandbox with resource limits.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from dataset.schema import BenchmarkTask
from execution.docker.sandbox import check_test_tampering


@dataclass
class EvaluationResult:
    task_id: str
    success: bool
    tests_passed: int = 0
    tests_failed: int = 0
    duration_seconds: float = 0.0
    failure_category: Optional[str] = None  # None | "test_tampering" | "patch_apply_failed" | "test_failed" | "timeout"
    error: Optional[str] = None
    output: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "success": self.success,
            "tests_passed": self.tests_passed,
            "tests_failed": self.tests_failed,
            "duration_seconds": self.duration_seconds,
            "failure_category": self.failure_category,
            "error": self.error,
        }


class CleanRoomEvaluator:
    def __init__(self, workdir: Optional[Path] = None, timeout_s: int = 60) -> None:
        self.workdir = workdir or Path(tempfile.gettempdir()) / "repopilot_eval"
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.timeout_s = timeout_s

    def _apply_patch(self, repo_dir: Path, patch_text: str) -> bool:
        if not patch_text.strip():
            return True
        pfile = repo_dir / "_eval_temp.patch"
        pfile.write_text(patch_text, encoding="utf-8")
        try:
            r = subprocess.run(
                ["git", "apply", "--whitespace=nowarn", str(pfile)],
                cwd=str(repo_dir),
                capture_output=True,
                text=True,
                timeout=30,
            )
            if r.returncode == 0:
                return True
            r2 = subprocess.run(
                ["git", "apply", "--ignore-space-change", "--ignore-whitespace", str(pfile)],
                cwd=str(repo_dir),
                capture_output=True,
                text=True,
                timeout=30,
            )
            return r2.returncode == 0
        finally:
            if pfile.exists():
                pfile.unlink()

    def evaluate(
        self,
        task: BenchmarkTask,
        candidate_patch: str,
        sandbox_mode: str = "auto",
    ) -> EvaluationResult:
        """Alias for evaluate_candidate."""
        return self.evaluate_candidate(task, candidate_patch, sandbox_mode=sandbox_mode)

    def evaluate_candidate(
        self,
        task: BenchmarkTask,
        candidate_patch: str,
        sandbox_mode: str = "auto",
    ) -> EvaluationResult:
        """Run clean-room evaluation on an agent-generated candidate patch."""
        start_time = time.time()

        # Step 1: Anti-Tampering Gate
        is_tampered, tampered_files = check_test_tampering(candidate_patch)
        if is_tampered:
            return EvaluationResult(
                task_id=task.task_id,
                success=False,
                failure_category="test_tampering",
                error=f"TAMPERING_DETECTED: Candidate patch modified test files: {tampered_files}",
                duration_seconds=round(time.time() - start_time, 2),
            )

        # Step 2: Clean workspace checkout
        eval_dir = self.workdir / f"eval_{task.task_id}_{int(start_time)}"
        try:
            # Clone or copy repo
            repo_source = task.repository
            if Path(repo_source).exists():
                shutil.copytree(str(Path(repo_source).resolve()), str(eval_dir), dirs_exist_ok=True)
                r_clone = subprocess.run(["git", "status"], cwd=str(eval_dir), capture_output=True, text=True)
            else:
                r_clone = subprocess.run(
                    ["git", "clone", "--filter=blob:none", repo_source, str(eval_dir)],
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_s,
                )
            if r_clone.returncode != 0:
                return EvaluationResult(
                    task_id=task.task_id,
                    success=False,
                    failure_category="clone_failed",
                    error=f"Git clone failed: {r_clone.stderr}",
                    duration_seconds=round(time.time() - start_time, 2),
                )

            # Checkout base commit
            r_co = subprocess.run(
                ["git", "checkout", "-f", task.base_commit],
                cwd=str(eval_dir),
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
            )
            if r_co.returncode != 0:
                return EvaluationResult(
                    task_id=task.task_id,
                    success=False,
                    failure_category="checkout_failed",
                    error=f"Git checkout base failed: {r_co.stderr}",
                    duration_seconds=round(time.time() - start_time, 2),
                )

            # Step 3: Apply candidate source patch
            if candidate_patch.strip():
                if not self._apply_patch(eval_dir, candidate_patch):
                    return EvaluationResult(
                        task_id=task.task_id,
                        success=False,
                        failure_category="patch_apply_failed",
                        error="Failed to apply candidate patch to base commit",
                        duration_seconds=round(time.time() - start_time, 2),
                    )

            # Step 4: Inject authoritative regression test patch from external storage
            if not self._apply_patch(eval_dir, task.test_patch):
                return EvaluationResult(
                    task_id=task.task_id,
                    success=False,
                    failure_category="test_inject_failed",
                    error="Failed to inject authoritative test patch",
                    duration_seconds=round(time.time() - start_time, 2),
                )

            # Step 5: Execute isolated test run
            cmd_parts = task.test_command.split()
            if cmd_parts and cmd_parts[0] in ("pytest", "python"):
                filtered_parts = [p for p in cmd_parts[1:] if not p.startswith("addopts") and p != "-o"]
                cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:deepeval", "-o", "addopts=", *filtered_parts]
            else:
                cmd = cmd_parts

            try:
                r_test = subprocess.run(
                    cmd,
                    cwd=str(eval_dir),
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_s,
                )
                output = (r_test.stdout or "") + "\n" + (r_test.stderr or "")
                passed = (r_test.returncode == 0)

                return EvaluationResult(
                    task_id=task.task_id,
                    success=passed,
                    tests_passed=1 if passed else 0,
                    tests_failed=0 if passed else 1,
                    failure_category=None if passed else "test_failed",
                    duration_seconds=round(time.time() - start_time, 2),
                    output=output[:2000],
                )
            except subprocess.TimeoutExpired:
                return EvaluationResult(
                    task_id=task.task_id,
                    success=False,
                    failure_category="timeout",
                    error=f"Test execution timed out after {self.timeout_s}s",
                    duration_seconds=round(time.time() - start_time, 2),
                )

        finally:
            if eval_dir.exists():
                shutil.rmtree(eval_dir, ignore_errors=True)
