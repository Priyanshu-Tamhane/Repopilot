"""Experiment 5 — LLM & Context Caching (Spec §16).

Measures efficiency gains from exact and semantic prompt caching:
- Exact SHA-256 hash matching on (model, system_prompt, prompt)
- 0ms latency, 0 billed tokens, and $0 cost on cache hits
- Compares repeated and overlapping maintenance tasks to measure cache_hit_rate and total tokens saved.
"""
from __future__ import annotations

EXPERIMENT = {
    "name": "exp5_caching",
    "description": "LLM response and prompt caching ablation (hit rate, token & cost savings)",
    "agent": "cached_agent",
    "dataset": "repopilot-seed v1.0",
    "config": {
        "retrieval": True,
        "multi_agent": True,
        "model_routing": True,
        "caching": True,
        "cache_ttl": 3600,
        "parallel": False,
        "workers": 1,
    },
}
