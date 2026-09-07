from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

@dataclass
class SandboxResult:
    repo_path: Path
    cleanup: callable


def _docker_available() -> bool:
    try:
        import docker  # type: ignore

        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


def prepare_sandbox(repo_url_or_path: str, workdir: str | None = None, mode: str = "auto") -> SandboxResult:
    """Prepare isolated execution environment.

    mode:
     - auto: use docker if available, else local temp clone
     - docker: force docker (raises if unavailable)
     - local: force local temp (fast, no isolation)
    """
    from retrieval.indexer.loader import clone_repository

    if mode == "docker" and not _docker_available():
        raise RuntimeError("Docker requested but not available")

    use_docker = False
    if mode == "auto":
        use_docker = _docker_available()
    elif mode == "docker":
        use_docker = True

    if use_docker:
        return _prepare_docker_sandbox(repo_url_or_path, workdir)
    else:
        return _prepare_local_sandbox(repo_url_or_path, workdir)


def _prepare_local_sandbox(repo_url_or_path: str, workdir: str | None) -> SandboxResult:
    from retrieval.indexer.loader import clone_repository

    repo_path = clone_repository(repo_url_or_path, workdir=workdir)

    def cleanup():
        # remove parent task dir
        parent = repo_path.parent
        if parent.exists():
            shutil.rmtree(parent, ignore_errors=True)

    return SandboxResult(repo_path=repo_path, cleanup=cleanup)


def _prepare_docker_sandbox(repo_url_or_path: str, workdir: str | None) -> SandboxResult:
    """For Phase 1, docker sandbox still clones locally but runs tests inside docker container via docker exec.
    Full isolation (clone inside container) will be added in Phase 6 with workers.
    Here we simulate: clone locally then mount into python:3.11-slim container for test runs.
    """
    # For now fallback to local clone; actual docker test execution is handled in run_tests_in_sandbox
    return _prepare_local_sandbox(repo_url_or_path, workdir)


def run_tests_in_sandbox(repo_path: Path, mode: str = "auto") -> tuple[int, int, str]:
    """Run pytest in sandbox. Returns (passed, failed, output).

    If docker mode, runs pytest inside docker container with volume mount.
    """
    use_docker = False
    if mode == "auto":
        use_docker = _docker_available()
    elif mode == "docker":
        use_docker = True

    if use_docker:
        return _run_tests_docker(repo_path)
    else:
        return _run_tests_local(repo_path)


def _run_tests_local(repo_path: Path) -> tuple[int, int, str]:
    try:
        result = subprocess.run(
            ["python", "-m", "pytest", "-q"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = (result.stdout or "") + "\n" + (result.stderr or "")
        return _parse_pytest_output(output)
    except subprocess.TimeoutExpired:
        return 0, 1, "pytest timed out after 120s"
    except FileNotFoundError:
        return 0, 1, "pytest not found"


def _run_tests_docker(repo_path: Path) -> tuple[int, int, str]:
    try:
        import docker  # type: ignore

        client = docker.from_env()
        # Run python:3.11-slim with mount
        # Use absolute posix path; on Windows need conversion
        host_path = str(repo_path.resolve())
        # Docker on Windows expects //c/... style, but docker sdk handles it
        output = client.containers.run(
            "python:3.11-slim",
            command="bash -c 'pip install -q pytest && pytest -q'",
            volumes={host_path: {"bind": "/repo", "mode": "rw"}},
            working_dir="/repo",
            remove=True,
            mem_limit="1g",
            stdout=True,
            stderr=True,
        )
        text = output.decode("utf-8", errors="ignore") if isinstance(output, bytes) else str(output)
        return _parse_pytest_output(text)
    except Exception as e:
        # Fallback to local
        return 0, 1, f"docker test run failed: {e}\nFalling back to local parser"


def _parse_pytest_output(output: str) -> tuple[int, int, str]:
    import re

    passed = failed = 0
    # pytest -q summary: "1 failed, 2 passed in 0.12s" or "3 passed in 0.05s"
    m = re.search(r"(\d+)\s+passed", output)
    if m:
        passed = int(m.group(1))
    m = re.search(r"(\d+)\s+failed", output)
    if m:
        failed = int(m.group(1))
    # If no summary but exit-like, try alternative
    if "passed" not in output and "failed" not in output:
        if "FAILED" in output:
            failed = output.count("FAILED")
        if "PASSED" in output:
            passed = output.count("PASSED")
    # If still 0/0 but output mentions "no tests collected", treat as 0/0
    return passed, failed, output


def get_git_patch(repo_path: Path) -> str:
    """Collect git diff patch after modifications."""
    try:
        result = subprocess.run(
            ["git", "diff"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=10,
        )
        patch = result.stdout or ""
        # Also untracked files
        result2 = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=10,
        )
        untracked = [x for x in (result2.stdout or "").splitlines() if x.strip()]
        # filter pycache and binary artifacts from patch
        untracked = [f for f in untracked if not any(s in f for s in ["__pycache__", ".pyc", ".pytest_cache", ".venv"])]
        for f in untracked:
            try:
                p = repo_path / f
                if p.suffix in (".pyc", ".pyo"):
                    continue
                content = p.read_text(encoding="utf-8", errors="ignore")
                patch += f"\n--- untracked: {f}\n+++ b/{f}\n{content}\n"
            except Exception:
                pass
        # If repo was not git (copied local without .git), just diff against original? Fallback: return file content hash
        if not patch.strip():
            # try git status
            result3 = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result3.stdout:
                patch = result3.stdout
        return patch
    except Exception as e:
        return f"# patch collection failed: {e}"
