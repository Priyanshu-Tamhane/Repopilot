"""Experiment 6 — Worker Scaling & Concurrency (Spec §16).

Measures parallel throughput scaling and queue latency across worker pool sizes:
- 1 worker: baseline sequential throughput (~10-12 tasks/min)
- 2 workers: concurrent scaling (~20-24 tasks/min)
- 4 workers: high throughput (~40-45 tasks/min)
- 8 workers: maximum concurrency scaling (~70+ tasks/min)
Tracks queue wait time (queue_latency) and concurrency speedup curve.
"""
from __future__ import annotations

EXPERIMENT = {
    "name": "exp6_scaling",
    "description": "Parallel worker pool scaling and queue latency ablation (1/2/4/8 workers)",
    "agent": "parallel_workers",
    "dataset": "repopilot-seed v1.0",
    "config": {
        "retrieval": True,
        "multi_agent": True,
        "model_routing": True,
        "caching": True,
        "parallel": True,
        "worker_tiers": [1, 2, 4, 8],
    },
}
