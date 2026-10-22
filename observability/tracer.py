"""RepoPilot Observability - Span Tracer for Subagent Execution Steps.

Measures timing and metadata for execution phases:
- RAG retrieval
- Multi-agent subagents (Planner, Researcher, Implementer, Tester, Debugger, Reviewer)
- Model routing decisions
- Cache lookups
- Pytest sandbox executions
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional


class Span:
    """Represents a single timing span for a step in task execution."""

    def __init__(self, name: str, parent_id: Optional[str] = None) -> None:
        self.name: str = name
        self.parent_id: Optional[str] = parent_id
        self.start_time: float = time.time()
        self.end_time: Optional[float] = None
        self.duration_seconds: float = 0.0
        self.status: str = "running"
        self.metadata: Dict[str, Any] = {}

    def finish(self, status: str = "ok", **kwargs: Any) -> None:
        """Mark span complete and record duration."""
        self.end_time = time.time()
        self.duration_seconds = round(self.end_time - self.start_time, 4)
        self.status = status
        self.metadata.update(kwargs)

    def to_dict(self) -> Dict[str, Any]:
        """Convert span to dictionary."""
        return {
            "name": self.name,
            "duration_seconds": self.duration_seconds,
            "status": self.status,
            "metadata": self.metadata,
        }


class SpanTracer:
    """Tracing context manager for tracking sub-steps of a task."""

    def __init__(self, task_id: str) -> None:
        self.task_id: str = task_id
        self.spans: List[Span] = []
        self._current_span: Optional[Span] = None

    def start_span(self, name: str) -> Span:
        """Start a new span."""
        span = Span(name)
        self.spans.append(span)
        self._current_span = span
        return span

    def finish_span(self, span: Span, status: str = "ok", **kwargs: Any) -> None:
        """Finish an existing span."""
        span.finish(status=status, **kwargs)

    def to_list(self) -> List[Dict[str, Any]]:
        """Return list of span dicts."""
        return [s.to_dict() for s in self.spans]
