"""Experiment 1 — Naive baseline (Spec §15).

Single agent, large model (Groq llama-3.3-70b or mock), no retrieval,
no caching. Control group for the ablation study (§17).
Exps 2-6 reuse the same dataset + runner entry point.
"""
from __future__ import annotations

EXPERIMENT = {
    "name": "exp1_baseline",
    "description": "Naive single agent, large model, no retrieval, no caching",
    "agent": "baseline",
    "dataset": "repopilot-seed v1.0",
    "config": {
        "retrieval": False,
        "multi_agent": False,
        "model_routing": False,
        "caching": False,
        "parallel": False,
    },
}
