"""Experiment 3 — Multi-Agent System (Spec §15).

Collaborative team of 6 specialized agents:
Planner -> Researcher -> Implementer <-> Tester <-> Debugger -> Reviewer
With self-correction repair loop (max 3 retries) and invariant code review.
Compare vs Exp1 & Exp2 on success rate, repair efficiency, and token usage.
"""
from __future__ import annotations

EXPERIMENT = {
    "name": "exp3_multi_agent",
    "description": "Multi-agent system (6 specialized agents with debugger repair loop & code reviewer)",
    "agent": "multi_agent",
    "dataset": "repopilot-seed v1.0",
    "config": {
        "retrieval": True,
        "multi_agent": True,
        "max_retries": 3,
        "model_routing": False,
        "caching": False,
        "parallel": False,
        "roles": ["planner", "researcher", "implementer", "tester", "debugger", "reviewer"],
    },
}
