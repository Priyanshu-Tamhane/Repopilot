"""Experiment 4 — Model Routing & Cost Optimization (Spec §16).

Dynamic task complexity classification + tiered model routing:
- Tier 1 (Cheap): Fast lightweight model (e.g. openai/gpt-oss-20b or llama-3.1-8b-instant, $0.05/$0.15 per M tokens)
- Tier 2 (Heavy): Flagship deep reasoning model (e.g. openai/gpt-oss-120b, $0.15/$0.60 per M tokens)
- Cascade escalation: escalates from Tier 1 to Tier 2 if tests fail during repair loop.

Compare vs Exp1, Exp2, and Exp3 on:
- Success rate (must not regress)
- Cost reduction (target 40-70% lower cost on easy/moderate tasks)
- Repair efficiency
"""
from __future__ import annotations

EXPERIMENT = {
    "name": "exp4_routing",
    "description": "Dynamic task complexity classification and tiered model routing with cascade escalation",
    "agent": "multi_agent_routed",
    "dataset": "repopilot-seed v1.0",
    "config": {
        "retrieval": True,
        "multi_agent": True,
        "model_routing": True,
        "cheap_model": "openai/gpt-oss-20b",
        "heavy_model": "openai/gpt-oss-120b",
        "max_retries": 3,
        "caching": False,
        "parallel": False,
    },
}
