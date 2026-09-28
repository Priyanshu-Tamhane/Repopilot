from __future__ import annotations

import time
from typing import Any

from agents.protocol import SharedTaskState, extract_json
from execution.docker.sandbox import get_git_patch
from inference.models.base import LLMProvider

REVIEWER_SYSTEM_PROMPT = """You are the Reviewer Agent in RepoPilot.
Your role is to inspect the final git diff patch before it is delivered to the user.

Checklist:
1. Does the patch actually address the issue?
2. Is the patch minimal, clean, and free of extraneous changes?
3. Are test files untouched? (Test files MUST NEVER be modified or deleted).
4. Output JSON ONLY in this format:
{
  "approved": true,
  "confidence": "high|medium|low",
  "notes": "summary of review feedback"
}
"""


class ReviewerAgent:
    """Reviewer Agent: inspects the git diff patch for quality, correctness, and safety invariants."""

    def __init__(self, provider: LLMProvider):
        self.provider = provider

    async def run(self, state: SharedTaskState) -> dict[str, Any]:
        t0 = time.time()
        state.tool_calls += 1

        # Extract git patch
        patch = get_git_patch(state.repo_path)
        state.patch = patch

        # Invariant 1: Empty patch cannot be approved if tests failed
        if not patch.strip() and state.test_failed > 0:
            state.approved = False
            state.review_notes = "Empty patch and tests failed."
            state.trace.add_step("reviewer", (time.time() - t0) * 1000, detail="rejected: empty patch")
            return {"approved": False, "notes": state.review_notes}

        # Invariant 2: Safety guard - test files must not be modified in the patch
        patch_lines = patch.splitlines()
        modified_test_files = [
            line for line in patch_lines
            if line.startswith("+++ b/") and any(t in line.lower() for t in ("test_", "_test.py", "tests/"))
        ]
        if modified_test_files:
            state.approved = False
            state.review_notes = f"Security rejection: test files were modified: {modified_test_files}"
            state.trace.add_step("reviewer", (time.time() - t0) * 1000, detail="rejected: tests modified")
            return {"approved": False, "notes": state.review_notes}

        # Mock / Fast approval if tests passed
        if state.use_mock or self.provider.model_name.startswith("mock"):
            is_approved = (state.test_failed == 0 and (state.test_passed > 0 or bool(patch.strip())))
            notes = "Patch verified: tests passing and no test files modified." if is_approved else "Tests failed."
            state.approved = is_approved
            state.review_notes = notes
            state.trace.add_step(
                "reviewer",
                (time.time() - t0) * 1000,
                detail=f"approved={is_approved} patch_len={len(patch)}",
            )
            return {"approved": is_approved, "notes": notes}

        prompt = f"""ISSUE:
{state.issue}

=== GIT DIFF PATCH ===
{patch[:4000]}

=== TEST RESULTS ===
Passed: {state.test_passed}, Failed: {state.test_failed}

Review this patch and provide judgment in JSON format."""

        resp = await self.provider.generate(prompt, system=REVIEWER_SYSTEM_PROMPT, max_tokens=1024)
        cost = self.provider.estimate_cost(resp.input_tokens, resp.output_tokens)
        state.record_llm_call(resp, cost, step_name="reviewer")

        data = extract_json(resp.content)
        approved = data.get("approved", state.test_failed == 0)
        notes = data.get("notes", "Patch reviewed.")

        state.approved = approved
        state.review_notes = notes
        state.trace.add_step(
            "reviewer",
            (time.time() - t0) * 1000,
            detail=f"approved={approved} notes={notes[:60]}",
        )
        return {"approved": approved, "notes": notes}
