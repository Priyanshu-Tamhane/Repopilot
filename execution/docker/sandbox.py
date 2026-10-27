from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

MAX_OUTPUT_CHARS = 50_000


def validate_safe_path(base_dir: Path, target_path: Path | str) -> Path:
    """Validate that target_path does not escape base_dir via symlinks or ../ traversal."""
    resolved_base = base_dir.resolve()
    resolved_target = (base_dir / target_path).resolve() if not Path(target_path).is_absolute() else Path(target_path).resolve()
    try:
        resolved_target.relative_to(resolved_base)
    except ValueError:
        raise PermissionError(f"SecurityError: Path escape attempt detected outside sandbox: {target_path}")
    return resolved_target


def check_test_tampering(patch_text: str) -> tuple[bool, list[str]]:
    """Scan candidate patch and detect any modifications to test files.
    
    Returns (is_tampered, list_of_tampered_test_files).
    """
    import re
    tampered = []
    lines = patch_text.splitlines()
    for line in lines:
        m = re.match(r"^(?:diff --git a/[^\s]+ b/|--- [ab]/|\+\+\+ [ab]/)([^\s]+)", line)
        if m:
            file_path = m.group(1).lstrip("/").lower()
            if any(t in file_path for t in ["test_", "_test.py", "tests/", "/test/"]):
                if file_path not in tampered:
                    tampered.append(file_path)
    return (len(tampered) > 0), tampered


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


def _run_tests_local(repo_path: Path, timeout_s: int = 60) -> tuple[int, int, str]:
    import sys
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-o", "addopts="],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        output = (result.stdout or "") + "\n" + (result.stderr or "")
        if len(output) > MAX_OUTPUT_CHARS:
            output = output[:MAX_OUTPUT_CHARS] + "\n... [OUTPUT TRUNCATED BY SANDBOX MONITOR]"
        return _parse_pytest_output(output)
    except subprocess.TimeoutExpired:
        return 0, 1, f"pytest timed out after {timeout_s}s (infinite loop terminated)"
    except FileNotFoundError:
        return 0, 1, "pytest not found"


def _run_tests_docker(repo_path: Path, timeout_s: int = 60, network: str = "none") -> tuple[int, int, str]:
    try:
        import docker  # type: ignore

        import os

        client = docker.from_env()
        host_path = os.path.realpath(str(repo_path))
        output = client.containers.run(
            "python:3.11-slim",
            command="bash -c 'pytest -q -o addopts= || true'",
            volumes={host_path: {"bind": "/repo", "mode": "rw"}},
            working_dir="/repo",
            remove=True,
            network_mode=network,
            mem_limit="2g",
            nano_cpus=2_000_000_000,
            pids_limit=100,
            stdout=True,
            stderr=True,
        )
        text = output.decode("utf-8", errors="ignore") if isinstance(output, bytes) else str(output)
        if len(text) > MAX_OUTPUT_CHARS:
            text = text[:MAX_OUTPUT_CHARS] + "\n... [OUTPUT TRUNCATED BY SANDBOX MONITOR]"
        return _parse_pytest_output(text)
    except Exception:
        # Fallback to local
        return _run_tests_local(repo_path, timeout_s=timeout_s)


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
