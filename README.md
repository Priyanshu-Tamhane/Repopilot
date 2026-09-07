# RepoPilot

Evaluation-driven coding-agent infrastructure that measures and improves efficiency of repository maintenance.

> **Spec:** `POST /tasks {repository, issue} → {success, patch, tests_passed, duration_seconds, input_tokens, ... }`
> **Focus:** retrieval, model routing, caching, parallel execution, sandboxing, observability — with ablation study.

## Build Order (Spec §21)

- **Phase 1 — DONE:** FastAPI → GitHub loader → Docker sandbox → single-agent baseline → solve one issue
- **Phase 2:** Benchmark runner → metrics → 20-task evaluation
- **Phase 3:** Repository indexing → RAG → compare vs baseline
- **Phase 4:** Multi-agent system
- **Phase 5:** Model routing + cost optimization
- **Phase 6:** Caching + parallel execution + worker scaling
- **Phase 7:** Observability → dashboard → ablation → final report

## Quick Start (Phase 1)

```bash
pip install -e ".[dev]"
cp .env.example .env  # set GROQ_API_KEY (https://console.groq.com/keys) or keep LLM_MOCK=true for offline
uvicorn api.main:app --reload --port 8000
```

### API

```bash
curl -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{"repository": "https://github.com/user/repo", "issue": "Fix bug in calculator.py: add() returns wrong value for negatives"}'

# Or local path for testing:
curl -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{"repository": "C:\\path\\to\\local\\repo", "issue": "Fix issue #1"}'
```

Health: `GET /health` , Metrics: `GET /metrics`

## Project Structure (Spec §20)

```
api/routes|schemas|dependencies
agents/planner|researcher|implementer|tester|debugger|reviewer|baseline
retrieval/indexer|embeddings|ast|graph
inference/router|models|cache|telemetry
execution/docker|workers|queue
evaluation/datasets|runner|metrics|experiments
observability/
```

## Baseline Agent (Phase 1 - Naive)

`Issue → Large LLM (Groq openai/gpt-oss-120b) → Repo exploration → Modify code → Run tests → Return patch`
No RAG, routing, caching, or parallelization. Control group for ablation.

LLM provider: **Groq** (`GROQ_API_KEY` + `GROQ_MODEL=openai/gpt-oss-120b`, OpenAI-compatible via `https://api.groq.com/openai/v1`). Falls back to OpenAI if needed.

Mock mode: `LLM_MOCK=true` uses heuristic patcher so you can test E2E without API keys.

## Tests

```bash
pytest -v
pytest tests/test_api.py -v
pytest tests/test_baseline_e2e.py -v  # builds a dummy repo and solves one issue
```
