from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from typing import Optional

from api.schemas.tasks import TaskResponse


@dataclass
class TaskRecord:
    task_id: str
    repository: str
    issue: str
    status: str  # queued | running | done | failed
    result: Optional[TaskResponse] = None


class TaskManager:
    """Phase 1: In-memory synchronous manager.

    Phase 6 will replace with Redis queue + Docker workers (1/2/4/8 workers).
    API spec says FastAPI → Queue → Workers → Docker containers.
    For Phase 1 we run directly but keep abstraction for future scaling.
    """

    def __init__(self):
        self.tasks: dict[str, TaskRecord] = {}

    async def submit(self, repository: str, issue: str) -> TaskResponse:
        task_id = uuid.uuid4().hex[:12]
        record = TaskRecord(task_id=task_id, repository=repository, issue=issue, status="queued")
        self.tasks[task_id] = record

        start = time.time()
        record.status = "running"
        try:
            # Import here to avoid circular
            from agents.baseline.agent import BaselineAgent
            from api.dependencies.config import get_settings

            settings = get_settings()
            # Priority: Groq if GROQ_API_KEY set, else OpenAI fallback
            if settings.groq_api_key:
                provider = "groq"
                model = settings.groq_model
                api_key = settings.groq_api_key
                base_url = settings.groq_base_url
            elif settings.llm_provider == "groq":
                provider = "groq"
                model = settings.groq_model
                api_key = settings.groq_api_key
                base_url = settings.groq_base_url
            else:
                provider = settings.llm_provider
                model = settings.openai_model
                api_key = settings.openai_api_key
                base_url = "https://api.openai.com/v1"
            agent = BaselineAgent(
                workdir=settings.workdir,
                sandbox_mode=settings.sandbox_mode,
                use_mock=settings.llm_mock,
                model=model,
                api_key=api_key,
                provider=provider,
                base_url=base_url,
            )
            result = await agent.run(repository, issue)
            result.trace = result.trace or {}
            result.trace["task_id"] = task_id
            record.result = result
            record.status = "done" if result.success else "failed"
            return result
        except Exception as e:
            import traceback

            duration = time.time() - start
            err_resp = TaskResponse(
                success=False,
                patch="",
                tests_passed=0,
                tests_failed=0,
                duration_seconds=duration,
                input_tokens=0,
                output_tokens=0,
                llm_calls=0,
                tool_calls=0,
                estimated_cost=0.0,
                error=f"{e}\n{traceback.format_exc()}",
            )
            record.result = err_resp
            record.status = "failed"
            return err_resp


_manager: Optional[TaskManager] = None


def get_task_manager() -> TaskManager:
    global _manager
    if _manager is None:
        _manager = TaskManager()
    return _manager
