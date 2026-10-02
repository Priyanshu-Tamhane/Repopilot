from __future__ import annotations

import asyncio
import hashlib
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Optional

from inference.models.base import LLMResponse


@dataclass
class CacheEntry:
    content: str
    model: str
    input_tokens: int
    output_tokens: int
    cost: float
    created_at: float
    hits: int = 0


class LLMCache:
    """Thread-safe, LRU in-memory response cache with TTL for LLM inferences (Spec §6 & §16).

    Hashes (model, system, prompt) using SHA-256.
    Provides instant hits (0ms latency, $0 token cost) for repeated or overlapping calls.
    """

    def __init__(self, max_size: int = 1000, default_ttl: float = 3600.0):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._entries: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = asyncio.Lock()

        # Telemetry counters
        self.hits: int = 0
        self.misses: int = 0
        self.tokens_saved: int = 0  
        self.cost_saved: float = 0.0

    @staticmethod
    def compute_key(model: str, system: str, prompt: str) -> str:
        raw = f"{model.strip()}|||{system.strip()}|||{prompt.strip()}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    async def get(self, model: str, system: str, prompt: str) -> Optional[LLMResponse]:
        key = self.compute_key(model, system, prompt)
        async with self._lock:
            if key not in self._entries:
                self.misses += 1
                return None

            entry = self._entries[key]
            # Check TTL expiry
            if time.time() - entry.created_at > self.default_ttl:
                del self._entries[key]
                self.misses += 1
                return None

            # Mark LRU hit: move to end
            self._entries.move_to_end(key)
            entry.hits += 1
            self.hits += 1
            saved_tokens = entry.input_tokens + entry.output_tokens
            self.tokens_saved += saved_tokens
            self.cost_saved += entry.cost

            # Return simulated 0ms cached LLMResponse
            return LLMResponse(
                content=entry.content,
                input_tokens=0,           # 0 fresh tokens billed
                output_tokens=0,
                model=f"{entry.model} (cached)",
                latency_ms=0.5,
            )

    async def set(
        self,
        model: str,
        system: str,
        prompt: str,
        response: LLMResponse,
        cost: float = 0.0,
    ) -> None:
        key = self.compute_key(model, system, prompt)
        async with self._lock:
            # Enforce max LRU size
            if len(self._entries) >= self.max_size and key not in self._entries:
                self._entries.popitem(last=False)  # evict least recently used

            self._entries[key] = CacheEntry(
                content=response.content,
                model=response.model,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                cost=cost,
                created_at=time.time(),
            )
            self._entries.move_to_end(key)

    async def clear(self) -> None:
        async with self._lock:
            self._entries.clear()
            self.hits = 0
            self.misses = 0
            self.tokens_saved = 0
            self.cost_saved = 0.0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return round(self.hits / total, 4) if total > 0 else 0.0

    def stats(self) -> dict[str, Any]:
        total = self.hits + self.misses
        return {
            "total_requests": total,
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": self.hit_rate,
            "tokens_saved": self.tokens_saved,
            "cost_saved": round(self.cost_saved, 5),
            "current_size": len(self._entries),
            "max_size": self.max_size,
        }


# Global singleton
_GLOBAL_CACHE: Optional[LLMCache] = None


def get_llm_cache() -> LLMCache:
    global _GLOBAL_CACHE
    if _GLOBAL_CACHE is None:
        _GLOBAL_CACHE = LLMCache()
    return _GLOBAL_CACHE


class CachedLLMProvider:
    """Transparent caching wrapper around any LLMProvider."""

    def __init__(self, provider: Any, cache: Optional[LLMCache] = None):
        self.provider = provider
        self.cache = cache or get_llm_cache()
        self.model_name = getattr(provider, "model_name", "unknown")

    async def generate(self, prompt: str, system: str = "", max_tokens: int = 2048) -> LLMResponse:
        cached = await self.cache.get(self.model_name, system, prompt)
        if cached is not None:
            return cached
        resp = await self.provider.generate(prompt, system=system, max_tokens=max_tokens)
        cost = self.provider.estimate_cost(resp.input_tokens, resp.output_tokens)
        await self.cache.set(self.model_name, system, prompt, resp, cost=cost)
        return resp

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        return self.provider.estimate_cost(input_tokens, output_tokens)

