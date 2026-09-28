from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from inference.models.base import LLMProvider, LLMResponse
from inference.telemetry.metrics import LLMCallRecord, TaskTrace


@dataclass
class SharedTaskState:
    """The shared whiteboard state passed between all agents in the team."""

    repository: str
    issue: str
    repo_path: Path
    sandbox_mode: str = "auto"
    use_mock: bool = True

    # Planner outputs
    plan: dict[str, Any] = field(default_factory=dict)

    # Researcher outputs
    candidate_files: list[str] = field(default_factory=list)
    relevant_tests: list[str] = field(default_factory=list)
    research_context: str = ""

    # Implementer outputs
    edits_applied: list[str] = field(default_factory=list)

    # Tester outputs
    test_passed: int = 0
    test_failed: int = 0
    test_output: str = ""

    # Debugger outputs
    iteration: int = 0
    max_retries: int = 3
    debug_history: list[dict[str, Any]] = field(default_factory=list)
    latest_debug_hint: str = ""

    # Reviewer outputs
    approved: bool = False
    review_notes: str = ""
    patch: str = ""

    # Telemetry
    trace: TaskTrace = field(default_factory=lambda: TaskTrace(task_id="pending", repository="", issue=""))
    tool_calls: int = 0
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_cost: float = 0.0

    def record_llm_call(self, resp: LLMResponse, cost: float, step_name: str) -> None:
        self.llm_calls += 1
        self.input_tokens += resp.input_tokens
        self.output_tokens += resp.output_tokens
        self.total_cost += cost
        self.trace.llm_calls.append(
            LLMCallRecord(
                model=resp.model,
                input_tokens=resp.input_tokens,
                output_tokens=resp.output_tokens,
                latency_ms=resp.latency_ms,
                cost=cost,
                success=resp.success,
            )
        )
        self.trace.add_step(step_name, resp.latency_ms, detail=resp.model)


def extract_json(text: str) -> dict[str, Any]:
    """Robust helper to extract JSON from raw LLM responses, stripping code fences."""
    cleaned = text.strip()
    if "```" in cleaned:
        m = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.DOTALL | re.IGNORECASE)
        if m:
            cleaned = m.group(1).strip()
    try:
        return json.loads(cleaned)
    except Exception:
        # Try to find first { and last }
        first = cleaned.find("{")
        last = cleaned.rfind("}")
        if first != -1 and last != -1 and last > first:
            try:
                return json.loads(cleaned[first : last + 1])
            except Exception:
                pass
    return {}
