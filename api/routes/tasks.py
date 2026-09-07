from __future__ import annotations

from fastapi import APIRouter, Depends

from api.dependencies.config import get_settings
from api.schemas.tasks import TaskRequest, TaskResponse
from execution.queue.manager import get_task_manager

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("", response_model=TaskResponse)
async def create_task(payload: TaskRequest):
    """POST /tasks {repository, issue} -> TaskResponse (Spec §2)

    Phase 1: synchronous execution (FastAPI -> Task Manager -> BaselineAgent -> Result)
    Phase 6: will enqueue to Redis + workers
    """
    manager = get_task_manager()
    result = await manager.submit(payload.repository, payload.issue)
    return result
