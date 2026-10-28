"""RepoPilot - Benchmark Run Record & Schema (Phase 4).

Defines the authoritative Per-Run JSON schema for all benchmark evaluations.
Every task attempt produces a persistent, reproducible JSON record that allows
offline report generation without model re-invocation.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


# Standard documented pricing per 1M tokens (from docs/architecture.md Decision 2)
MODEL_PRICING: Dict[str, Dict[str, float]] = {
    # Groq models
    "llama-3.3-70b-versatile": {"input": 0.59, "output": 0.79},
    "llama-3.1-8b-instant": {"input": 0.05, "output": 0.08},
    "openai/gpt-oss-120b": {"input": 0.59, "output": 0.79},
    "openai/gpt-oss-20b": {"input": 0.05, "output": 0.08},
    # OpenAI models
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    # Mock offline provider
    "mock": {"input": 0.0, "output": 0.0},
    "mock-gpt-4o-mini": {"input": 0.0, "output": 0.0},
    "mock-gpt-4o-mini-cheap": {"input": 0.0, "output": 0.0},
}


def calculate_cost(model_name: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate exact cost in USD based on documented pricing table."""
    pricing = MODEL_PRICING.get(model_name, MODEL_PRICING["mock"])
    cost = (input_tokens / 1_000_000 * pricing["input"]) + (output_tokens / 1_000_000 * pricing["output"])
    return round(cost, 6)


@dataclass
class EvaluationSummary:
    """Independent evaluation results produced by CleanRoomEvaluator."""
    resolved: bool
    tests_passed: int = 0
    tests_failed: int = 0
    failure_category: Optional[str] = None  # none | test_failure | test_tampering | patch_apply_failed | timeout
    error: Optional[str] = None
    output_preview: str = ""


@dataclass
class BenchmarkRunRecord:
    """Complete, self-contained record of a single benchmark task attempt."""
    run_id: str
    task_id: str
    timestamp: str
    status: str  # "resolved" | "failed" | "error"
    agent_config: str  # "b0_baseline" | "b1_retrieval" | "b2_multi_agent" | "b3_routing"
    model_id: str
    provider: str
    pricing: Dict[str, float]
    base_commit: str
    duration_seconds: float
    input_tokens: int
    output_tokens: int
    estimated_cost: float
    tool_calls: int
    retries: int
    patch: str
    patch_hash: str
    evaluation: EvaluationSummary
    environment: Dict[str, str] = field(default_factory=dict)
    diagnostic_notes: str = ""
    trace: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        run_id: str,
        task_id: str,
        agent_config: str,
        model_id: str,
        provider: str,
        base_commit: str,
        duration_seconds: float,
        input_tokens: int,
        output_tokens: int,
        tool_calls: int,
        retries: int,
        patch: str,
        evaluation: EvaluationSummary,
        diagnostic_notes: str = "",
        trace: Optional[Dict[str, Any]] = None,
    ) -> BenchmarkRunRecord:
        pricing = MODEL_PRICING.get(model_id, {"input": 0.0, "output": 0.0})
        cost = calculate_cost(model_id, input_tokens, output_tokens)
        patch_hash = hashlib.sha256(patch.encode("utf-8")).hexdigest() if patch else ""
        status = "resolved" if evaluation.resolved else ("error" if evaluation.failure_category in ("patch_apply_failed", "timeout") else "failed")

        env = {
            "python_version": sys.version.split()[0],
            "os_platform": platform.platform(),
            "cpu_count": str(os.cpu_count() or 1),
        }

        return cls(
            run_id=run_id,
            task_id=task_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            status=status,
            agent_config=agent_config,
            model_id=model_id,
            provider=provider,
            pricing=pricing,
            base_commit=base_commit,
            duration_seconds=round(duration_seconds, 3),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost=cost,
            tool_calls=tool_calls,
            retries=retries,
            patch=patch,
            patch_hash=patch_hash,
            evaluation=evaluation,
            environment=env,
            diagnostic_notes=diagnostic_notes,
            trace=trace or {},
        )

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def save(self, out_dir: Path) -> Path:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        file_name = f"{self.task_id}_{self.agent_config}_{self.run_id}.json"
        target_path = out_dir / file_name
        target_path.write_text(self.to_json(), encoding="utf-8")
        return target_path

    @classmethod
    def load(cls, path: Path | str) -> BenchmarkRunRecord:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        eval_data = data.pop("evaluation", {})
        evaluation = EvaluationSummary(**eval_data)
        return cls(evaluation=evaluation, **data)
