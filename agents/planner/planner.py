from __future__ import annotations

import json
import time
from typing import Any

from agents.protocol import SharedTaskState, extract_json
from inference.models.base import LLMProvider

PLANNER_SYSTEM_PROMPT = """You are the Planner Agent in RepoPilot.
Your role is to analyze a reported repository issue, diagnose the likely bug category,
and generate a clear, step-by-step strategy for the Researcher and Implementer agents.

Output JSON ONLY with the following schema:
{
  "category": "e.g. arithmetic, off_by_one, division_by_zero, missing_function, etc.",
  "target_hint": "filename or function name hinted in the issue",
  "expected_behavior": "what the code should do when fixed",
  "steps": [
    "step 1: identify file and buggy line",
    "step 2: write the fix",
    "step 3: ensure tests pass"
  ]
}
"""


class PlannerAgent:
    def __init__(self, provider: LLMProvider):
        self.provider = provider

    async def run(self, state: SharedTaskState) -> dict[str, Any]:
        t0 = time.time()

        if state.use_mock or self.provider.model_name.startswith("mock"):
            plan = self._mock_plan(state.issue)
            state.plan = plan
            state.trace.add_step("planner", (time.time() - t0) * 1000, detail=f"category={plan.get('category')}")
            return plan

        prompt = f"""ISSUE DESCRIPTION:
{state.issue}

Provide a structured plan to resolve this issue in the specified JSON format."""

        resp = await self.provider.generate(prompt, system=PLANNER_SYSTEM_PROMPT, max_tokens=1024)
        cost = self.provider.estimate_cost(resp.input_tokens, resp.output_tokens)
        state.record_llm_call(resp, cost, step_name="planner")

        plan = extract_json(resp.content)
        if not plan:
            plan = {
                "category": "general_bug",
                "target_hint": "",
                "expected_behavior": "fix the bug according to the issue description",
                "steps": ["locate file", "apply minimal fix", "verify with tests"],
            }

        state.plan = plan
        return plan

    def _mock_plan(self, issue: str) -> dict[str, Any]:
        issue_lower = issue.lower()
        if "add" in issue_lower or "negative" in issue_lower:
            cat = "add_negatives"
            hint = "calculator.py / math_utils.py"
            expected = "add(a, b) should return a + b for all numbers including negative values"
        elif "subtract" in issue_lower:
            cat = "subtract"
            hint = "ops.py / calculator.py"
            expected = "subtract(a, b) should return a - b"
        elif "multiply" in issue_lower:
            cat = "multiply"
            hint = "calculator.py"
            expected = "multiply(a, b) should return a * b"
        elif "divide" in issue_lower and "zero" in issue_lower:
            cat = "divide_zero"
            hint = "calculator.py"
            expected = "divide(a, b) should raise ZeroDivisionError when b == 0"
        elif "off-by-one" in issue_lower or "off by one" in issue_lower:
            cat = "off_by_one"
            hint = "loop/range indexing"
            expected = "correct loop range without omitting last element"
        elif "reverse" in issue_lower:
            cat = "reverse"
            hint = "string reversal"
            expected = "return reversed string s[::-1]"
        elif "max" in issue_lower:
            cat = "max_value"
            hint = "max function"
            expected = "return maximum value, not minimum"
        elif "factorial" in issue_lower:
            cat = "factorial"
            hint = "factorial function"
            expected = "return 1 for base case n == 0"
        elif "average" in issue_lower:
            cat = "average"
            hint = "average function"
            expected = "divide by len(items) instead of len(items) + 1"
        else:
            cat = "general_bug"
            hint = ""
            expected = "resolve the issue"

        return {
            "category": cat,
            "target_hint": hint,
            "expected_behavior": expected,
            "steps": [
                f"Identify the relevant source file matching '{hint}'",
                f"Update implementation so that {expected}",
                "Run test suite to verify the fix",
            ],
        }
