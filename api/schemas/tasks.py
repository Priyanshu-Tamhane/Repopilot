from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class TaskRequest(BaseModel):
    repository: str = Field(..., description="GitHub URL or local path to repo")
    issue: str = Field(..., description="Issue description, e.g. 'Fix issue #123'")


class TaskResponse(BaseModel):
    success: bool
    patch: str = ""
    tests_passed: int = 0
    tests_failed: int = 0
    duration_seconds: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    llm_calls: int = 0
    tool_calls: int = 0
    estimated_cost: float = 0.0
    error: Optional[str] = None
    trace: Optional[dict] = None


class HealthResponse(BaseModel):
    status: str
    version: str
    sandbox_mode: str
    llm_mock: bool
