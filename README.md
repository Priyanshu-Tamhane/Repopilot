# RepoPilot

Evaluation-driven coding-agent infrastructure that measures and improves efficiency of repository maintenance.

> **Spec:** `POST /tasks {repository, issue} → {success, patch, tests_passed, duration_seconds, input_tokens, ... }`
> **Focus:** retrieval, model routing, caching, parallel execution, sandboxing, observability — with ablation study.

## Build Order (Spec §21)

- **Phase 1 — DONE:** FastAPI → GitHub loader → Docker sandbox → single-agent baseline → solve one issue
- **Phase 2 — DONE:** Benchmark runner → full Sec.16 metrics → 20-task seed evaluation (exp1_baseline: 20/20 mock)
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
Mock fix coverage (9 bug shapes): add-negatives, subtract/multiply not-implemented,
divide-by-zero guard, off-by-one, string reverse, max-returns-min, factorial base case,
average-divides-by-n+1. Target selection never touches test files (`test_*.py`,
`*_test.py`, `tests/` are skipped; `test_foo.py` remaps to `foo.py`), and only
files that actually change are recorded as edits.

## Phase 2 — Benchmark (20-task evaluation)

Fixed seed dataset: `evaluation/datasets/seed_tasks.json` (20 tasks x 9 bug categories,
each with buggy files, pytest suite, expected behavior, fail_to_pass ground truth).
Repos materialize to temp dirs at runtime — no network needed.

```bash
python -m evaluation.runner.cli --sandbox local            # full 20-task run
python -m evaluation.runner.cli --limit 3                  # smoke run
python -m evaluation.runner.cli --dataset path/to/ds.json  # custom dataset
```

Results land in `evaluation/results/exp1_baseline_<ts>.json + .md`
(metrics per Spec Sec.16: success/test-pass/patch rates, avg/median/p95 latency,
tokens, LLM calls, cost/task + cost/success, tool calls/task, tasks/min).
`evaluation/experiments/exp1_baseline.py` is the control-group descriptor
that Exps 2-6 will reuse against the same dataset.

### Latest result - exp1_baseline (mock LLM, local sandbox, 2026-09-09)

20/20 tasks pass. Wall time 17.5s for the full suite.

| Metric | Value |
|---|---|
| Task success rate | 100% (20/20) |
| Test pass rate | 100% |
| Patch rate | 100% |
| Avg / median / p95 latency | 0.63s / 0.61s / 0.82s |
| Total tokens (in/out) | 6506 (4865/1641) |
| Avg tokens per task | 325 |
| LLM calls (total/avg) | 20 / 1.0 |
| Cost per task / per success | $0.0001 / $0.0001 |
| Avg tool calls per task | 5.0 |
| Errors | 0 |
| Throughput | 68.6 tasks/min |

Note: 100% is the mock ceiling on synthetic bugs - it validates the harness,
not model skill. Real signal comes from Groq runs and Phase 7 ablation deltas.
Reproduce with: `$env:LLM_MOCK="true"; python -m evaluation.runner.cli --sandbox local`

## Tests

```bash
pytest -v
pytest tests/test_api.py -v
pytest tests/test_baseline_e2e.py -v  # builds a dummy repo and solves one issue
pytest tests/test_benchmark.py -v     # dataset validity (bugs fail pre-fix) + metrics math + 3-task mock run
```
