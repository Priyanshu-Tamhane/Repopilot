from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class LLMResponse:
    content: str
    input_tokens: int
    output_tokens: int
    model: str
    latency_ms: float
    success: bool = True
    error: Optional[str] = None


class LLMProvider:
    model_name: str = "unknown"

    async def generate(self, prompt: str, system: str = "", max_tokens: int = 2048) -> LLMResponse:
        raise NotImplementedError

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        # Default: mock pricing ~ $0.15 / 1M input, $0.60 / 1M output (gpt-4o-mini like)
        return (input_tokens * 0.15 + output_tokens * 0.60) / 1_000_000
