from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles

from api.dependencies.config import get_settings
from api.routes.tasks import router as tasks_router
from api.routes.dashboard import router as dashboard_router
from api.schemas.tasks import HealthResponse
from observability.telemetry import get_telemetry_collector

app = FastAPI(
    title="RepoPilot",
    description="Evaluation-driven coding-agent infrastructure - Phase 7 (React Dashboard & Observability)",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tasks_router)
app.include_router(dashboard_router)

# Mount React static assets if built dist exists
DIST_ASSETS = Path(__file__).resolve().parent.parent / "dashboard" / "dist" / "assets"
if DIST_ASSETS.exists():
    app.mount("/assets", StaticFiles(directory=str(DIST_ASSETS)), name="static_assets")


@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health():
    settings = get_settings()
    return HealthResponse(
        status="ok",
        version=app.version,
        sandbox_mode=settings.sandbox_mode,
        llm_mock=settings.llm_mock,
    )


@app.get("/metrics", response_class=PlainTextResponse, tags=["observability"])
async def metrics():
    """Return Prometheus text exposition format metrics."""
    telemetry = get_telemetry_collector()
    return PlainTextResponse(content=telemetry.to_prometheus_text(), media_type="text/plain")


@app.get("/", tags=["root"])
async def root():
    return {
        "name": "RepoPilot",
        "version": app.version,
        "phase": "7 - Observability & React Dashboard",
        "endpoints": ["POST /tasks", "GET /health", "GET /metrics", "GET /dashboard"],
        "docs": "/docs",
    }

