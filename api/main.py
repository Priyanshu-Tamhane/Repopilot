from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.dependencies.config import get_settings
from api.routes.tasks import router as tasks_router
from api.schemas.tasks import HealthResponse

app = FastAPI(
    title="RepoPilot",
    description="Evaluation-driven coding-agent infrastructure - Phase 1 baseline (Spec §21)",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tasks_router)


@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health():
    settings = get_settings()
    return HealthResponse(
        status="ok",
        version=app.version,
        sandbox_mode=settings.sandbox_mode,
        llm_mock=settings.llm_mock,
    )


@app.get("/metrics", tags=["observability"])
async def metrics():
    """Stub for Phase 7 Prometheus; returns basic counts."""
    from execution.queue.manager import get_task_manager

    manager = get_task_manager()
    total = len(manager.tasks)
    done = sum(1 for t in manager.tasks.values() if t.status == "done")
    failed = sum(1 for t in manager.tasks.values() if t.status == "failed")
    return {
        "tasks_total": total,
        "tasks_done": done,
        "tasks_failed": failed,
    }


@app.get("/", tags=["root"])
async def root():
    return {
        "name": "RepoPilot",
        "version": app.version,
        "phase": "1 - baseline",
        "endpoints": ["POST /tasks", "GET /health", "GET /metrics"],
        "docs": "/docs",
    }
