from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from agents.protocol import SharedTaskState
from inference.models.base import LLMProvider
from retrieval.indexer.indexer import build_index
from retrieval.indexer.loader import get_file_snapshot
from retrieval.retriever import retrieve


class ResearcherAgent:
    """Researcher Agent: navigates repository code, uses AST & TF-IDF indexing,

    and identifies target buggy files, dependency graphs, and linked test files.
    """

    def __init__(self, provider: LLMProvider, top_k: int = 6, char_budget: int = 8000):
        self.provider = provider
        self.top_k = top_k
        self.char_budget = char_budget

    async def run(self, state: SharedTaskState) -> dict[str, Any]:
        t0 = time.time()
        state.tool_calls += 1

        # Augment search query with target hint from planner
        target_hint = state.plan.get("target_hint", "") if state.plan else ""
        query = f"{state.issue} {target_hint}".strip()

        try:
            # Build AST + TF-IDF index
            index = build_index(state.repo_path)
            res = retrieve(
                index=index,
                query=query,
                repo_root=state.repo_path,
                top_k=self.top_k,
                expand=True,
                include_tests=True,
                char_budget=self.char_budget,
            )

            state.candidate_files = sorted(res.candidate_files)
            state.relevant_tests = res.relevant_tests
            state.research_context = res.context

            # If no candidates found (empty repo / fallback), snapshot whole repo
            if not state.research_context:
                state.research_context = get_file_snapshot(state.repo_path)
                state.candidate_files = [p.name for p in state.repo_path.glob("*.py")]

            summary = {
                "candidate_files": state.candidate_files,
                "relevant_tests": state.relevant_tests,
                "context_length": len(state.research_context),
                "ranked_chunks": res.stats.get("ranked", 0),
            }

        except Exception as e:
            # Fallback to naive snapshot if indexing fails
            state.research_context = get_file_snapshot(state.repo_path)
            state.candidate_files = [p.name for p in state.repo_path.glob("*.py")]
            summary = {
                "candidate_files": state.candidate_files,
                "relevant_tests": [],
                "context_length": len(state.research_context),
                "error": str(e),
            }

        state.trace.add_step(
            "researcher",
            (time.time() - t0) * 1000,
            detail=f"candidates={state.candidate_files} tests={state.relevant_tests}",
        )
        return summary
