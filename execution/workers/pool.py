from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any, List, Optional, TypeVar

T = TypeVar("T")
R = TypeVar("R")


@dataclass
class WorkerExecutionResult:
    result: Any
    worker_id: int
    queue_latency_ms: float
    execution_latency_ms: float
    success: bool
    error: Optional[str] = None


class WorkerPool:
    """Parallel execution worker pool with concurrency scaling and queue latency tracking (Spec §6 & §14).

    Controls concurrent task execution across 1, 2, 4, or 8 workers.
    Measures queue wait time (queue_latency) and concurrency throughput scaling.
    """

    def __init__(self, concurrency: int = 1, timeout_s: float = 300.0):
        if concurrency < 1:
            raise ValueError("Concurrency must be at least 1")
        self.concurrency = concurrency
        self.timeout_s = timeout_s
        self.semaphore = asyncio.Semaphore(concurrency)
        self._active_workers: int = 0
        self._peak_workers: int = 0
        self._worker_counter: int = 0
        self._lock = asyncio.Lock()

        # Telemetry
        self.completed_tasks: int = 0
        self.failed_tasks: int = 0
        self.total_queue_latency_ms: float = 0.0

    @property
    def avg_queue_latency_s(self) -> float:
        total = self.completed_tasks + self.failed_tasks
        return round((self.total_queue_latency_ms / total) / 1000.0, 4) if total > 0 else 0.0

    async def execute(
        self,
        task_fn: Callable[[], Coroutine[Any, Any, R]],
    ) -> tuple[R, float]:
        """Execute task within worker pool. Returns (result, queue_latency_seconds)."""
        submit_time = time.time()

        # Wait in queue until a worker slot is free
        async with self.semaphore:
            pickup_time = time.time()
            queue_latency_ms = (pickup_time - submit_time) * 1000.0

            async with self._lock:
                self._active_workers += 1
                self._worker_counter += 1
                worker_id = self._worker_counter
                if self._active_workers > self._peak_workers:
                    self._peak_workers = self._active_workers

            try:
                result = await asyncio.wait_for(task_fn(), timeout=self.timeout_s)
                async with self._lock:
                    self.completed_tasks += 1
                    self.total_queue_latency_ms += queue_latency_ms
                return result, round(queue_latency_ms / 1000.0, 4)
            except Exception as e:
                async with self._lock:
                    self.failed_tasks += 1
                    self.total_queue_latency_ms += queue_latency_ms
                raise e
            finally:
                async with self._lock:
                    self._active_workers -= 1

    async def map(
        self,
        items: List[T],
        task_fn: Callable[[T], Coroutine[Any, Any, R]],
    ) -> List[tuple[R, float]]:
        """Run a collection of tasks concurrently bounded by worker concurrency."""
        coros = [self.execute(lambda item=item: task_fn(item)) for item in items]
        return await asyncio.gather(*coros)

    def stats(self) -> dict[str, Any]:
        return {
            "concurrency": self.concurrency,
            "active_workers": self._active_workers,
            "peak_workers": self._peak_workers,
            "completed_tasks": self.completed_tasks,
            "failed_tasks": self.failed_tasks,
            "avg_queue_latency_s": self.avg_queue_latency_s,
        }
