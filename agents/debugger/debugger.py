from __future__ import annotations

import time
from typing import Any

from agents.protocol import SharedTaskState, extract_json
from inference.models.base import LLMProvider

DEBUGGER_SYSTEM_PROMPT = """You are the Debugger Agent in RepoPilot.
Your role is to diagnose failed unit test outputs from pytest and provide concrete,
actionable guidance to the Implementer agent on how to correct the code.

Rules:
1. Identify the exact failing assertion or exception from the pytest output.
2. Explain the root cause of why the current code produced this failure.
3. Provide concise, specific instructions on what lines to change.
4. Output JSON ONLY in this format:
{
  "failing_test": "test name that failed",
  "root_cause": "brief diagnosis of why it failed",
  "suggested_fix": "exact instructions for the Implementer to fix the code"
}
"""


class DebuggerAgent:
    """Debugger Agent: analyzes pytest failure tracebacks and provides targeted feedback for re-implementation."""

    def __init__(self, provider: LLMProvider):
        self.provider = provider

    async def run(self, state: SharedTaskState) -> str:
        t0 = time.time()

        if state.use_mock or self.provider.model_name.startswith("mock"):
            hint = self._mock_diagnosis(state)
            state.latest_debug_hint = hint
            state.debug_history.append({"iteration": state.iteration, "hint": hint})
            state.trace.add_step(
                f"debugger_iter_{state.iteration}",
                (time.time() - t0) * 1000,
                detail=f"hint={hint[:80]}",
            )
            return hint

        prompt = f"""ISSUE:
{state.issue}

=== PYTEST FAILURE OUTPUT ===
{state.test_output[:3000]}

Diagnose the failure and provide instructions for the Implementer in JSON format."""

        resp = await self.provider.generate(prompt, system=DEBUGGER_SYSTEM_PROMPT, max_tokens=1024)
        cost = self.provider.estimate_cost(resp.input_tokens, resp.output_tokens)
        state.record_llm_call(resp, cost, step_name=f"debugger_iter_{state.iteration}")

        data = extract_json(resp.content)
        if data and "suggested_fix" in data:
            hint = f"Fix {data.get('failing_test', '')}: {data.get('root_cause', '')}. Instructions: {data.get('suggested_fix', '')}"
        else:
            hint = f"The previous fix resulted in failed tests:\n{state.test_output[:500]}\nPlease carefully re-read the issue and correct the implementation."

        state.latest_debug_hint = hint
        state.debug_history.append({"iteration": state.iteration, "hint": hint})
        return hint

    def _mock_diagnosis(self, state: SharedTaskState) -> str:
        out = state.test_output.lower()
        if "assert 0 ==" in out or "notimplemented" in out:
            return "Function is not implemented or returning 0. Make sure the calculation returns the correct result."
        elif "zerodivisionerror" in out:
            return "A ZeroDivisionError was raised unhandled. Add a guard: if b == 0: raise ZeroDivisionError."
        elif "assertionerror" in out:
            return "Assertion failed. Verify the return value against the expected test behavior."
        return "Unit tests failed. Please review the failed assertions and update the implementation."
