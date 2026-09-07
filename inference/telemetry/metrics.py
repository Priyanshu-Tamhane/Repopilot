from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class LLMCallRecord:
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    cost: float
    success: bool


@dataclass
class TaskTrace:
    task_id: str
    repository: str
    issue: str
    started_at: float = field(default_factory=time.time)
    steps: List[dict] = field(default_factory=list)
    llm_calls: List[LLMCallRecord] = field(default_factory=list)
    tool_calls: int = 0

    def add_step(self, name: str, duration_ms: float, detail: str = ""):
        self.steps.append({"name": name, "duration_ms": duration_ms, "detail": detail})

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "repository": self.repository,
            "issue": self.issue,
            "steps": self.steps,
            "llm_calls": [r.__dict__ for r in self.llm_calls],
            "tool_calls": self.tool_calls,
            "total_input_tokens": sum(c.input_tokens for c in self.llm_calls),
            "total_output_tokens": sum(c.output_tokens for c in self.llm_calls),
            "total_cost": sum(c.cost for c in self.llm_calls),
        }
