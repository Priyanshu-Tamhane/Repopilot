from __future__ import annotations

import os
import shutil
import tempfile
import uuid
from pathlib import Path


def is_valid_url(url: str) -> bool:
    return url.startswith("http://") or url.startswith("https://") or url.startswith("git@")


def clone_repository(repo_url_or_path: str, workdir: str | None = None) -> Path:
    """Clone GitHub repo or copy local repo to a temp isolated directory.

    Returns Path to cloned repo root.
    Supports:
    - https://github.com/user/repo[.git]
    - local path (for testing)
    """
    base = Path(workdir) if workdir else Path(tempfile.gettempdir()) / "repopilot"
    base.mkdir(parents=True, exist_ok=True)
    dest = base / f"task_{uuid.uuid4().hex[:8]}"
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / "repo"

    # Local path: copy
    if os.path.exists(repo_url_or_path):
        src = Path(repo_url_or_path).resolve()
        if src.is_file():
            raise ValueError(f"repository path is a file, expected directory: {src}")
        shutil.copytree(src, target, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", ".venv", "venv", ".mypy_cache", ".pytest_cache"))
        # Ensure .git is present for patch collection; if not, init it
        if not (target / ".git").exists():
            import subprocess

            subprocess.run(["git", "init"], cwd=str(target), capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(target), capture_output=True)
            subprocess.run(["git", "config", "user.name", "test"], cwd=str(target), capture_output=True)
            subprocess.run(["git", "add", "."], cwd=str(target), capture_output=True)
            subprocess.run(["git", "commit", "-m", "snapshot"], cwd=str(target), capture_output=True)
        return target

    # Remote: git clone
    if is_valid_url(repo_url_or_path):
        # Use GitPython if available, else fallback to subprocess
        try:
            from git import Repo

            Repo.clone_from(repo_url_or_path, str(target))
            return target
        except Exception:
            import subprocess

            result = subprocess.run(
                ["git", "clone", repo_url_or_path, str(target)],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0:
                raise RuntimeError(f"git clone failed: {result.stderr}") from None
            return target

    raise ValueError(f"Invalid repository: {repo_url_or_path} (must be GitHub URL or local path)")


def get_file_snapshot(repo_path: Path, max_files: int = 100) -> str:
    """Build a lightweight repo snapshot for naive baseline (no vector DB yet).

    Returns concatenated file listing + truncated file contents.
    This is the naive 'full-repo in context' attempt that Phase 1 uses as control.
    Phase 3 will replace this with RAG.
    """
    lines: list[str] = []
    lines.append(f"Repository: {repo_path}")
    # listing
    all_files = []
    for p in repo_path.rglob("*"):
        if p.is_file():
            rel = p.relative_to(repo_path).as_posix()
            if any(x in rel for x in [".git/", "__pycache__", ".venv", "node_modules", ".pytest_cache"]):
                continue
            all_files.append((rel, p))
    all_files.sort(key=lambda x: x[0])
    lines.append(f"Total files: {len(all_files)}")
    for rel, _ in all_files[:max_files]:
        lines.append(f" - {rel}")
    if len(all_files) > max_files:
        lines.append(f" ... and {len(all_files)-max_files} more files")

    # include contents of python files (limited)
    lines.append("\n=== FILE CONTENTS (truncated) ===")
    for rel, p in all_files:
        if p.suffix in (".py", ".md", ".txt", ".toml", ".cfg", ".json", ".yaml", ".yml"):
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            if len(text) > 5000:
                text = text[:5000] + "\n... [truncated]"
            lines.append(f"\nFILE: {rel}\n```\n{text}\n```")
            if len("\n".join(lines)) > 12000:
                lines.append("\n... [snapshot truncated for token limits]")
                break
    return "\n".join(lines)
