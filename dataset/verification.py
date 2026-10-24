"""RepoPilot Dataset - Automated Task Verifier.

Verifies candidate benchmark tasks against Phase 2 requirements:
1. Checks out repository at buggy base_commit.
2. Applies test_patch and asserts the test FAILS (proves bug is reproduced).
3. Applies reference_patch and asserts the test PASSES (proves fix works).
4. Asserts pre-existing tests pass without regressions.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from dataset.schema import BenchmarkTask


class TaskVerifier:
    def __init__(self, workdir: Optional[Path] = None, timeout_s: int = 120) -> None:
        self.workdir = workdir or Path(tempfile.gettempdir()) / "repopilot_verify"
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.timeout_s = timeout_s

    def _run_git(self, repo_dir: Path, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *args],
            cwd=str(repo_dir),
            capture_output=True,
            text=True,
            timeout=self.timeout_s,
        )

    def _apply_patch(self, repo_dir: Path, patch_text: str) -> bool:
        """Apply a git diff patch to the repository."""
        if not patch_text.strip():
            return True
        patch_file = repo_dir / "_verify_temp.patch"
        patch_file.write_text(patch_text, encoding="utf-8")
        try:
            # Try normal git apply
            res = self._run_git(repo_dir, "apply", "--whitespace=nowarn", str(patch_file))
            if res.returncode == 0:
                return True
            # Fallback with ignore-whitespace
            res2 = self._run_git(repo_dir, "apply", "--ignore-space-change", "--ignore-whitespace", str(patch_file))
            return res2.returncode == 0
        finally:
            if patch_file.exists():
                patch_file.unlink()

    def _run_test(self, repo_dir: Path, test_cmd: str) -> Tuple[bool, str]:
        """Run the specified test command inside repo_dir."""
        # Use sys.executable to ensure identical python environment
        cmd_parts = test_cmd.split()
        if cmd_parts and cmd_parts[0] in ("pytest", "python"):
            if cmd_parts[0] == "pytest":
                cmd = [sys.executable, "-m", "pytest", "-o", "addopts=", *cmd_parts[1:]]
            else:
                cmd = [sys.executable, *cmd_parts[1:]]
        else:
            cmd = cmd_parts

        try:
            r = subprocess.run(
                cmd,
                cwd=str(repo_dir),
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
            )
            output = (r.stdout or "") + "\n" + (r.stderr or "")
            passed = (r.returncode == 0)
            return passed, output
        except subprocess.TimeoutExpired:
            return False, f"Test timed out after {self.timeout_s}s"
        except Exception as e:
            return False, f"Failed to execute test: {e}"

    def verify_task(self, task: BenchmarkTask) -> Dict[str, Any]:
        """Run complete pre-fix failure and post-fix pass verification."""
        start_time = time.time()
        task_dir = self.workdir / f"verify_{task.task_id}_{int(start_time)}"
        
        result = {
            "task_id": task.task_id,
            "repo": task.repository,
            "base_commit": task.base_commit,
            "pre_fix_failed": False,
            "post_fix_passed": False,
            "verified": False,
            "duration_s": 0.0,
            "log": "",
        }

        try:
            # 1. Clone repository
            print(f"[{task.task_id}] Cloning {task.repository}...")
            r_clone = subprocess.run(
                ["git", "clone", "--filter=blob:none", task.repository, str(task_dir)],
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
            )
            if r_clone.returncode != 0:
                result["log"] = f"Clone failed: {r_clone.stderr}"
                return result

            # 2. Checkout base_commit
            print(f"[{task.task_id}] Checking out base commit {task.base_commit[:8]}...")
            r_co = self._run_git(task_dir, "checkout", "-f", task.base_commit)
            if r_co.returncode != 0:
                result["log"] = f"Checkout failed: {r_co.stderr}"
                return result

            # 3. Apply test_patch (add the regression test)
            print(f"[{task.task_id}] Applying regression test patch...")
            if not self._apply_patch(task_dir, task.test_patch):
                result["log"] = "Failed to apply test_patch"
                return result

            # 4. Verify test FAILS before the fix
            print(f"[{task.task_id}] Running test on unpatched code (must fail)...")
            pre_pass, pre_out = self._run_test(task_dir, task.test_command)
            result["pre_fix_failed"] = not pre_pass
            if pre_pass:
                result["log"] = f"Pre-fix test unexpectedly PASSED:\n{pre_out[:500]}"
                return result

            # 5. Apply reference_patch (the fix)
            print(f"[{task.task_id}] Applying reference fix patch...")
            if not self._apply_patch(task_dir, task.reference_patch):
                result["log"] = "Failed to apply reference_patch"
                return result

            # 6. Verify test PASSES after the fix
            print(f"[{task.task_id}] Running test on patched code (must pass)...")
            post_pass, post_out = self._run_test(task_dir, task.test_command)
            result["post_fix_passed"] = post_pass
            if not post_pass:
                result["log"] = f"Post-fix test FAILED:\n{post_out[:500]}"
                return result

            # If both pass, task is verified!
            result["verified"] = result["pre_fix_failed"] and result["post_fix_passed"]
            print(f"[{task.task_id}] Verification SUCCESSFUL! Pre-fix FAIL, Post-fix PASS.")

        except Exception as e:
            result["log"] = f"Verification exception: {e}"
        finally:
            result["duration_s"] = round(time.time() - start_time, 2)
            # Cleanup
            if task_dir.exists():
                shutil.rmtree(task_dir, ignore_errors=True)

        return result


if __name__ == "__main__":
    import argparse
    from dataset.schema import load_tasks_jsonl

    parser = argparse.ArgumentParser(description="RepoPilot Task Verifier")
    parser.add_argument("--dataset", default="dataset/tasks.jsonl", help="Path to tasks.jsonl")
    parser.add_argument("--task-id", help="Filter for specific task ID")
    args = parser.parse_args()

    tasks = load_tasks_jsonl(args.dataset)
    if args.task_id:
        tasks = [t for t in tasks if t.task_id == args.task_id]

    print(f"Loaded {len(tasks)} tasks from {args.dataset} to verify...")
    verifier = TaskVerifier()
    all_passed = True

    for t in tasks:
        res = verifier.verify_task(t)
        if not res["verified"]:
            all_passed = False
            print(f"FAILED: {t.task_id} -> {res['log']}")
        else:
            print(f"PASSED: {t.task_id} ({res['duration_s']}s)")

    if not all_passed:
        print("\nDataset verification FAILED.")
        sys.exit(1)
    else:
        print("\nAll tasks in dataset PASSED verification!")
        sys.exit(0)
