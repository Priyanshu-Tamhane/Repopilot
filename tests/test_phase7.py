"""RepoPilot - Phase 7 Test Suite.

Validates:
- TelemetryCollector Prometheus metrics formatting and counter math
- SpanTracer context manager for subagent step durations
- Ablation study matrix generator and markdown report
- FastAPI React dashboard routes & /metrics endpoint
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app
from observability.telemetry import TelemetryCollector, get_telemetry_collector
from observability.tracer import SpanTracer
from evaluation.experiments.ablation import generate_ablation_matrix, generate_ablation_report_markdown


def test_telemetry_collector_metrics():
    """Test TelemetryCollector metrics recording and summary statistics."""
    collector = TelemetryCollector()
    collector.reset()

    collector.record_task(
        success=True,
        duration=1.25,
        tokens_input=1000,
        tokens_output=200,
        tokens_saved=500,
        llm_calls=2,
        cost=0.00015,
        cached=True,
        model_tier="cheap",
    )

    collector.record_task(
        success=False,
        duration=2.50,
        tokens_input=2000,
        tokens_output=400,
        tokens_saved=0,
        llm_calls=4,
        cost=0.00060,
        cached=False,
        model_tier="heavy",
    )

    summary = collector.get_summary()
    assert summary["tasks_total"] == 2
    assert summary["tasks_success"] == 1
    assert summary["tasks_failed"] == 1
    assert summary["pass_rate_percent"] == 50.0
    assert summary["tokens_input"] == 3000
    assert summary["cache_hits"] == 1
    assert summary["cache_misses"] == 1
    assert summary["routing_cheap"] == 1
    assert summary["routing_heavy"] == 1


def test_prometheus_text_exposition():
    """Test Prometheus text exposition format generation."""
    collector = TelemetryCollector()
    collector.reset()
    collector.record_task(success=True, duration=0.8, tokens_input=500, cost=0.0001, cached=True)

    text = collector.to_prometheus_text()
    assert "# HELP repopilot_tasks_total" in text
    assert "repopilot_tasks_total 1" in text
    assert 'repopilot_routing_count{tier="cheap"} 1' in text
    assert "repopilot_cache_hits_total 1" in text


def test_span_tracer():
    """Test SpanTracer timing for execution steps."""
    tracer = SpanTracer(task_id="test-task-100")
    span1 = tracer.start_span("RAG Retrieval")
    tracer.finish_span(span1, status="ok", candidate_files=5)

    span2 = tracer.start_span("Pytest Sandbox")
    tracer.finish_span(span2, status="ok", passed=2)

    spans = tracer.to_list()
    assert len(spans) == 2
    assert spans[0]["name"] == "RAG Retrieval"
    assert spans[0]["metadata"]["candidate_files"] == 5
    assert spans[1]["name"] == "Pytest Sandbox"


def test_ablation_matrix_generator():
    """Test ablation study matrix generation and report rendering."""
    matrix = generate_ablation_matrix()
    assert len(matrix["experiments"]) == 6
    assert matrix["summary"]["total_phases_evaluated"] == 6
    assert matrix["summary"]["cost_reduction_percent"] == 28.6

    report = generate_ablation_report_markdown()
    assert "# RepoPilot — Full Ablation Study Report" in report
    assert "Exp 1: Baseline Agent" in report
    assert "Exp 6: Worker Pool Scaling" in report


def test_dashboard_routes_e2e():
    """Test FastAPI dashboard API endpoints and Prometheus route."""
    client = TestClient(app)

    # 1. /metrics
    resp_metrics = client.get("/metrics")
    assert resp_metrics.status_code == 200
    assert "repopilot_uptime_seconds" in resp_metrics.text

    # 2. /api/dashboard/summary
    resp_summary = client.get("/api/dashboard/summary")
    assert resp_summary.status_code == 200
    data_summary = resp_summary.json()
    assert "telemetry" in data_summary
    assert "tasks" in data_summary

    # 3. /api/dashboard/ablation
    resp_ablation = client.get("/api/dashboard/ablation")
    assert resp_ablation.status_code == 200
    data_ablation = resp_ablation.json()
    assert len(data_ablation["experiments"]) == 6

    # 4. /dashboard (React SPA HTML)
    resp_dashboard = client.get("/dashboard")
    assert resp_dashboard.status_code == 200
