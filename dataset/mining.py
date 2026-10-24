"""RepoPilot Dataset - GitHub Issue & PR Mining Tool.

Mines candidate bug-fixing tasks from real GitHub repositories:
1. Finds merged pull requests that fix bugs and include test changes.
2. Extracts base (buggy) commit SHA and merged (fixed) commit SHA.
3. Separates the reference code fix from the regression tests.
4. Outputs candidate task specifications ready for verification.
"""
from __future__ import annotations

import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

import httpx
from dotenv import load_dotenv

load_dotenv()

GITHUB_API = "https://api.github.com"


class GitHubMiner:
    def __init__(self, token: Optional[str] = None) -> None:
        self.token = token or os.getenv("GITHUB_TOKEN")
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "RepoPilot-Miner",
        }
        if self.token:
            self.headers["Authorization"] = f"token {self.token}"

    def get(self, url: str, params: Optional[Dict[str, Any]] = None) -> httpx.Response:
        full_url = url if url.startswith("http") else f"{GITHUB_API}{url}"
        r = httpx.get(full_url, headers=self.headers, params=params, timeout=20.0)
        r.raise_for_status()
        return r

    def get_pr_details(self, repo: str, pr_number: int) -> Dict[str, Any]:
        """Fetch PR info, commit SHAs, and diff."""
        pr = self.get(f"/repos/{repo}/pulls/{pr_number}").json()
        files = self.get(f"/repos/{repo}/pulls/{pr_number}/files").json()

        # Fetch diff directly from PR endpoint with diff Accept header
        diff_headers = dict(self.headers)
        diff_headers["Accept"] = "application/vnd.github.v3.diff"
        diff_resp = httpx.get(
            f"{GITHUB_API}/repos/{repo}/pulls/{pr_number}",
            headers=diff_headers,
            follow_redirects=True,
            timeout=25.0,
        )
        diff_text = diff_resp.text

        return {
            "pr": pr,
            "files": files,
            "diff": diff_text,
        }

    def separate_patches(self, diff_text: str) -> Tuple[str, str, List[str], List[str]]:
        """Separate raw diff into source patch and test patch.
        
        Returns:
            (reference_patch, test_patch, source_files, test_files)
        """
        # Split diff into per-file diff blocks
        file_diffs = re.split(r"(?=diff --git )", diff_text)
        src_diffs = []
        test_diffs = []
        src_files = []
        test_files = []

        for fdiff in file_diffs:
            if not fdiff.strip():
                continue
            # Match target filename
            m = re.search(r"diff --git a/[^\s]+ b/([^\s]+)", fdiff)
            if not m:
                continue
            filename = m.group(1)
            is_test = (
                "test" in filename.lower()
                or filename.startswith("tests/")
                or "/tests/" in filename
            )

            if is_test:
                test_diffs.append(fdiff)
                test_files.append(filename)
            else:
                src_diffs.append(fdiff)
                src_files.append(filename)

        return "".join(src_diffs), "".join(test_diffs), src_files, test_files

    def mine_candidates(
        self,
        repo: str,
        max_results: int = 10,
        search_query: str = "is:pr is:merged bug in:title",
    ) -> List[Dict[str, Any]]:
        """Search merged bug-fixing PRs in a repository."""
        query = f"repo:{repo} {search_query}"
        resp = self.get("/search/issues", params={"q": query, "per_page": max_results})
        items = resp.json().get("items", [])
        candidates = []

        for item in items:
            pr_num = item["number"]
            try:
                details = self.get_pr_details(repo, pr_num)
                pr = details["pr"]
                diff = details["diff"]
                src_patch, test_patch, src_files, test_files = self.separate_patches(diff)

                # Qualification filters:
                # 1. Must modify both code and test
                # 2. Must not touch too many files (keep task focused)
                # 3. Base commit and merge commit must exist
                if not src_patch or not test_patch:
                    continue
                if len(src_files) > 4 or len(test_files) > 3:
                    continue

                candidates.append({
                    "task_id": f"{repo.replace('/', '-')}-pr{pr_num}",
                    "repo": repo,
                    "pr_number": pr_num,
                    "title": item["title"],
                    "body": item["body"] or "",
                    "base_commit": pr["base"]["sha"],
                    "merge_commit": pr["merge_commit_sha"],
                    "head_commit": pr["head"]["sha"],
                    "src_files": src_files,
                    "test_files": test_files,
                    "src_patch": src_patch,
                    "test_patch": test_patch,
                })
            except Exception as e:
                print(f"Skipping PR #{pr_num} due to error: {e}", file=sys.stderr)

        return candidates


if __name__ == "__main__":
    miner = GitHubMiner()
    print("Testing GitHubMiner on msiemens/tinydb...")
    candidates = miner.mine_candidates("msiemens/tinydb", max_results=5)
    print(f"Found {len(candidates)} candidate tasks.")
    for c in candidates:
        print(f"  - [{c['task_id']}] {c['title']} (src: {c['src_files']}, test: {c['test_files']})")
