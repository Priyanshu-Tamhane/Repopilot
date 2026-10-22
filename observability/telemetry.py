"""RepoPilot Observability - Telemetry & Prometheus Metrics Collector.

Tracks real-time system metrics across all phases:
- Task counts, pass/fail rates, latency
- LLM calls, token usage, cost, tokens saved
- Cache hits vs misses (Phase 6)
- Dynamic model routing distribution (CHEAP vs HEAVY) (Phase 5)
- Worker queue latency (Phase 6)
"""
from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional


class TelemetryCollector:
    """Thread-safe telemetry and Prometheus metric collector."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tasks_total: int = 0
        self._tasks_success: int = 0
        self._tasks_failed: int = 0
        self._tokens_input: int = 0
        self._tokens_output: int = 0
        self._tokens_saved: int = 0
        self._llm_calls: int = 0
        self._cost_dollars: float = 0.0
        self._cache_hits: int = 0
        self._cache_misses: int = 0
        self._routing_cheap: int = 0
        self._routing_heavy: int = 0
        self._queue_latencies: List[float] = []
        self._task_durations: List[float] = []
        self._start_time: float = time.time()

    def record_task(
        self,
        success: bool,
        duration: float,
        tokens_input: int = 0,
        tokens_output: int = 0,
        tokens_saved: int = 0,
        llm_calls: int = 1,
        cost: float = 0.0,
        cached: bool = False,
        model_tier: str = "cheap",
    ) -> None:
        """Record a single task execution metric snapshot."""
        with self._lock:
            self._tasks_total += 1
            if success:
                self._tasks_success += 1
            else:
                self._tasks_failed += 1

            self._task_durations.append(duration)
            self._tokens_input += tokens_input
            self._tokens_output += tokens_output
            self._tokens_saved += tokens_saved
            self._llm_calls += llm_calls
            self._cost_dollars += cost

            if cached:
                self._cache_hits += 1
            else:
                self._cache_misses += 1

            if model_tier.lower() == "heavy":
                self._routing_heavy += 1
            else:
                self._routing_cheap += 1

    def record_cache_hit(self) -> None:
        with self._lock:
            self._cache_hits += 1

    def record_cache_miss(self) -> None:
        with self._lock:
            self._cache_misses += 1

    def record_queue_latency(self, latency_seconds: float) -> None:
        with self._lock:
            self._queue_latencies.append(latency_seconds)

    def get_summary(self) -> Dict[str, Any]:
        """Return a dictionary of aggregated telemetry metrics."""
        with self._lock:
            avg_duration = sum(self._task_durations) / len(self._task_durations) if self._task_durations else 0.0
            avg_queue = sum(self._queue_latencies) / len(self._queue_latencies) if self._queue_latencies else 0.0
            pass_rate = (self._tasks_success / self._tasks_total * 100.0) if self._tasks_total > 0 else 0.0
            cache_hit_rate = (self._cache_hits / (self._cache_hits + self._cache_misses) * 100.0) if (self._cache_hits + self._cache_misses) > 0 else 0.0

            return {
                "uptime_seconds": round(time.time() - self._start_time, 2),
                "tasks_total": self._tasks_total,
                "tasks_success": self._tasks_success,
                "tasks_failed": self._tasks_failed,
                "pass_rate_percent": round(pass_rate, 2),
                "avg_duration_seconds": round(avg_duration, 2),
                "avg_queue_latency_seconds": round(avg_queue, 3),
                "tokens_input": self._tokens_input,
                "tokens_output": self._tokens_output,
                "tokens_saved": self._tokens_saved,
                "llm_calls": self._llm_calls,
                "total_cost_dollars": round(self._cost_dollars, 6),
                "cache_hits": self._cache_hits,
                "cache_misses": self._cache_misses,
                "cache_hit_rate_percent": round(cache_hit_rate, 2),
                "routing_cheap": self._routing_cheap,
                "routing_heavy": self._routing_heavy,
            }

    def to_prometheus_text(self) -> str:
        """Format metrics in standard Prometheus text exposition format."""
        s = self.get_summary()
        lines = [
            "# HELP repopilot_uptime_seconds System uptime in seconds",
            "# TYPE repopilot_uptime_seconds counter",
            f"repopilot_uptime_seconds {s['uptime_seconds']}",
            "# HELP repopilot_tasks_total Total tasks executed",
            "# TYPE repopilot_tasks_total counter",
            f"repopilot_tasks_total {s['tasks_total']}",
            "# HELP repopilot_tasks_success Total successful task executions",
            "# TYPE repopilot_tasks_success counter",
            f"repopilot_tasks_success {s['tasks_success']}",
            "# HELP repopilot_tasks_failed Total failed task executions",
            "# TYPE repopilot_tasks_failed counter",
            f"repopilot_tasks_failed {s['tasks_failed']}",
            "# HELP repopilot_tokens_total Total LLM tokens processed",
            "# TYPE repopilot_tokens_total counter",
            f"repopilot_tokens_total{{type=\"input\"}} {s['tokens_input']}",
            f"repopilot_tokens_total{{type=\"output\"}} {s['tokens_output']}",
            f"repopilot_tokens_total{{type=\"saved\"}} {s['tokens_saved']}",
            "# HELP repopilot_cost_dollars Total estimated LLM cost in USD",
            "# TYPE repopilot_cost_dollars counter",
            f"repopilot_cost_dollars {s['total_cost_dollars']:.6f}",
            "# HELP repopilot_cache_hits_total Total LLM prompt cache hits",
            "# TYPE repopilot_cache_hits_total counter",
            f"repopilot_cache_hits_total {s['cache_hits']}",
            "# HELP repopilot_cache_misses_total Total LLM prompt cache misses",
            "# TYPE repopilot_cache_misses_total counter",
            f"repopilot_cache_misses_total {s['cache_misses']}",
            "# HELP repopilot_routing_count Total model routing decisions by tier",
            "# TYPE repopilot_routing_count counter",
            f"repopilot_routing_count{{tier=\"cheap\"}} {s['routing_cheap']}",
            f"repopilot_routing_count{{tier=\"heavy\"}} {s['routing_heavy']}",
            "# HELP repopilot_avg_duration_seconds Average task execution latency",
            "# TYPE repopilot_avg_duration_seconds gauge",
            f"repopilot_avg_duration_seconds {s['avg_duration_seconds']}",
        ]
        return "\n".join(lines) + "\n"

    def reset(self) -> None:
        """Reset all metrics (useful for testing)."""
        with self._lock:
            self._tasks_total = 0
            self._tasks_success = 0
            self._tasks_failed = 0
            self._tokens_input = 0
            self._tokens_output = 0
            self._tokens_saved = 0
            self._llm_calls = 0
            self._cost_dollars = 0.0
            self._cache_hits = 0
            self._cache_misses = 0
            self._routing_cheap = 0
            self._routing_heavy = 0
            self._queue_latencies.clear()
            self._task_durations.clear()
            self._start_time = time.time()


_GLOBAL_TELEMETRY = TelemetryCollector()


def get_telemetry_collector() -> TelemetryCollector:
    """Return the global TelemetryCollector instance."""
    return _GLOBAL_TELEMETRY
