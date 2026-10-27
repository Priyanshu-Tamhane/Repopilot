"""RepoPilot API - React Dashboard Routes & Static File Handler."""
from __future__ import annotations

from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import HTMLResponse, FileResponse
from observability.telemetry import get_telemetry_collector
from execution.queue.manager import get_task_manager

router = APIRouter(prefix="", tags=["dashboard"])

DIST_DIR = Path(__file__).resolve().parent.parent.parent / "dashboard" / "dist"


@router.get("/api/dashboard/summary")
async def get_dashboard_summary():
    """Return live metrics summary and task feed for React frontend."""
    telemetry = get_telemetry_collector()
    manager = get_task_manager()

    task_list = []
    for t in manager.tasks.values():
        task_list.append({
            "id": t.task_id,
            "issue": t.issue,
            "repo": t.repository,
            "status": t.status,
            "success": t.result.success if t.result else False,
            "testsPassed": t.result.tests_passed if t.result else 0,
            "testsFailed": t.result.tests_failed if t.result else 0,
            "durationSeconds": t.result.duration_seconds if t.result else 0.0,
            "modelTier": "CHEAP" if t.result and not t.result.trace.get("routing", {}).get("escalated") else "HEAVY",
            "cost": f"${t.result.estimated_cost:.5f}" if t.result else "$0.00000",
            "patch": t.result.patch if t.result else "",
        })

    return {
        "telemetry": telemetry.get_summary(),
        "tasks": task_list,
    }


@router.get("/api/dashboard/ablation")
async def get_dashboard_ablation():
    """Return 6-experiment ablation study matrix."""
    from evaluation.experiments.ablation import generate_ablation_matrix
    return generate_ablation_matrix()


@router.get("/dashboard", response_class=HTMLResponse)
@router.get("/dashboard/{full_path:path}", response_class=HTMLResponse)
async def serve_react_dashboard(full_path: str = ""):
    """Serve built React single-page application at /dashboard."""
    index_html = DIST_DIR / "index.html"
    if index_html.exists():
        return FileResponse(str(index_html))
    return HTMLResponse(
        content="<html><body><h2>React Dashboard build not found. Run <code>npm run build</code> in <code>dashboard/</code></h2></body></html>",
        status_code=200,
    )
