from __future__ import annotations

import json
import re
import time

from .base import LLMProvider, LLMResponse


class MockLLMProvider(LLMProvider):
    """Deterministic mock for Phase 1 testing without API keys.

    Heuristic: tries to return a JSON patch plan. The baseline agent will fall back to
    heuristic file edits if JSON parsing fails.
    """

    model_name = "mock-gpt-4o-mini"

    async def generate(self, prompt: str, system: str = "", max_tokens: int = 2048) -> LLMResponse:
        start = time.time()
        # Simple heuristic: extract file mentions and issue intent
        # Return a JSON with file_edits
        content = self._heuristic_response(prompt)
        latency_ms = (time.time() - start) * 1000
        # Rough token estimation: 1 token ~ 4 chars
        input_tokens = max(1, len(prompt) // 4)
        output_tokens = max(1, len(content) // 4)
        return LLMResponse(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=self.model_name,
            latency_ms=latency_ms,
        )

    def _heuristic_response(self, prompt: str) -> str:
        # Try to infer requested file from prompt
        # Look for markers like "FILE: path/to/file.py"
        files = re.findall(r"FILE:\s*([^\n]+)", prompt)
        # If issue mentions calculator, addition, etc. - provide generic fix
        issue_lower = prompt.lower()

        # Default: claim to fix the primary file
        target_file = files[0].strip() if files else "calculator.py"

        # Try to produce a plausible JSON action
        # The baseline agent will interpret this; if not parseable, it uses regex fallback
        plan = {
            "reasoning": "Mock LLM: analyzing issue and proposing patch",
            "file_edits": [
                {
                    "path": target_file,
                    "action": "heuristic_fix",
                    "instruction": "Fix the bug described in the issue. Look for off-by-one, missing negative handling, or not implemented functions.",
                }
            ],
            "tests_to_run": "pytest -q",
        }
        return json.dumps(plan, indent=2)
