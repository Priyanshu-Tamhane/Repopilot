# RepoPilot

Evaluation-driven coding-agent infrastructure that measures and improves efficiency of repository maintenance.

> **Spec:** `POST /tasks {repository, issue} → {success, patch, tests_passed, duration_seconds, input_tokens, ... }`
> **Focus:** retrieval, model routing, caching, parallel execution, sandboxing, observability — with ablation study.

## Build Order (Spec §21)

- **Phase 1 — DONE:** FastAPI → GitHub loader → Docker sandbox → single-agent baseline → solve one issue
- **Phase 2 — DONE:** Benchmark runner → full Sec.16 metrics → 20-task seed evaluation (exp1_baseline: 20/20 mock)
- **Phase 3 — DONE:** Repository indexing (AST + dependency graph + TF-IDF) → RAG (top-6, 8k budget) → Exp2 compare vs baseline (20/20 parity, retrieval hit@6 100%)
- **Phase 4 — DONE:** Multi-agent system (Planner, Researcher, Implementer, Tester, Debugger, Reviewer + Coordinator) → Exp3 evaluation
- **Phase 5 — DONE:** Dynamic model routing (CHEAP vs HEAVY tiers) + cascade escalation on failure → Exp4 evaluation (-28.6% cost reduction)
- **Phase 6:** Caching + parallel execution + worker scaling
- **Phase 7:** Observability → dashboard → ablation → final report

## Quick Start (Phase 1)

```bash
pip install -e ".[dev]"
cp .env.example .env  # set GROQ_API_KEY or keep LLM_MOCK=true for offline
```

### Unified CLI (`repopilot.py`)

RepoPilot provides a single, unified command-center entry point for the entire project:

```bash
# 1. Run demo with mock (offline) or real Groq LLM
python repopilot.py demo --mock --task easy
python repopilot.py demo --real --task easy

# 2. Run on any custom repository and issue
python repopilot.py run --repo /path/to/repo --issue "Fix bug description" --phase 5 --real

# 3. Run benchmarks across phases (1=Baseline, 2=RAG, 3=Multi-Agent, 4=Routing)
python repopilot.py benchmark --exp 4 --limit 3 --real

# 4. Compare benchmark metrics and cost savings
python repopilot.py compare

# 5. Start the FastAPI server
python repopilot.py serve --port 8000

# 6. Run the test suite
python repopilot.py test
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
python -m evaluation.runner.cli --sandbox local            # Exp1 - full 20-task baseline
python -m evaluation.runner.cli --retrieval --sandbox local # Exp2 - same tasks with RAG
python -m evaluation.runner.cli --limit 3                  # smoke run
python -m evaluation.runner.cli --dataset path/to/ds.json  # custom dataset
python -m evaluation.experiments.compare evaluation/results/exp1_*.json evaluation/results/exp2_*.json
```

Results land in `evaluation/results/exp1_baseline_<ts>.json + .md`
(metrics per Spec Sec.16: success/test-pass/patch rates, avg/median/p95 latency,
tokens, LLM calls, cost/task + cost/success, tool calls/task, tasks/min).
`evaluation/experiments/exp1_baseline.py` is the control-group descriptor
that Exps 2-6 will reuse against the same dataset.

### Latest result - exp1_baseline vs exp2_retrieval (mock LLM, local sandbox, 2026-09-18)

Both 20/20 on the fixed 20-task seed (wall ~17-18s). Seed repos are 2 files each, so retrieval parity is expected; savings scale on real 50-file repos.

| Metric | Exp1 Baseline | Exp2 Retrieval | Delta |
|---|---:|---:|---|
| Task success rate | 100% (20/20) | 100% (20/20) | +0.0% PASS |
| Test pass rate | 100% | 100% | +0.0% |
| Avg / median / p95 latency | 0.85s / 0.84s / 0.99s | 0.91s / 0.92s / 1.06s | +7% (indexing overhead) |
| Total tokens | 6506 | 6583 | +1.2% (tiny-repo parity; measure via `trace.retrieval`) |
| Avg tokens/task | 325 | 329 | +1.2% |
| LLM calls | 20 / 1.0 | 20 / 1.0 | +0.0% |
| Cost/task | $0.0001 | $0.0001 | +0.0% |
| Retrieval hit@6 | — | 100% (20/20 buggy file in candidate set) | — |
| Throughput | 49.4 tasks/min | 46.9 tasks/min | -5% |

Compare with: `python -m evaluation.experiments.compare evaluation/results/exp1_*.json evaluation/results/exp2_*.json`
Reproduce: `$env:LLM_MOCK="true"; python -m evaluation.runner.cli --sandbox local` and `--retrieval --sandbox local`

## Phase 3 — Retrieval / RAG

Replaces baseline full-snapshot (`get_file_snapshot`) with `Issue -> TF-IDF rank -> top-6 files -> 1-hop import expansion -> relevant tests -> 8k-char LLM context`.

Structure: `retrieval/ast/parser.py` (functions/classes/imports), `retrieval/graph/dependencies.py` (import graph + test mapping), `retrieval/embeddings/tfidf.py` (TF-IDF + cosine), `retrieval/indexer/indexer.py` (chunking + RepoIndex save/load), `retrieval/retriever.py` (retrieve pipeline). Agent seam `agents/baseline/agent.py:use_retrieval` (default off, baseline path untouched). Trace records `retrieval:{candidate_files, context_chars, full_snapshot_chars, context_tokens_est}` so "tokens saved" is measurable without double runs.

Run: `python -m evaluation.runner.cli --retrieval --sandbox local` (Exp2) — see `evaluation/experiments/exp2_retrieval.py` and compare.

## Phase 4 — Multi-Agent System (Exp3)

Orchestrates 6 specialized agents working together:
- **Planner:** Diagnoses issue category and devises repair strategy
- **Researcher:** Explores candidate files, imports, and relevant unit tests
- **Implementer:** Writes clean, minimal code fixes
- **Tester:** Executes pytest in isolated sandbox
- **Debugger:** Diagnoses pytest failures and provides root-cause feedback for retries (max 3 rounds)
- **Reviewer:** Invariant gatekeeper inspecting git diff before acceptance (rejects test tampering or empty diffs)

Run: `python -m evaluation.runner.cli --multi-agent --sandbox local`

## Phase 5 — Dynamic Model Routing & Cost Optimization (Exp4)

Intelligent tiered model selection based on task complexity and keyword analysis:
- **Tier 1 (Cheap):** `openai/gpt-oss-20b` or `llama-3.1-8b-instant` ($0.05 / $0.15 per M tokens)
- **Tier 2 (Heavy):** `openai/gpt-oss-120b` or flagship LLMs ($0.15 / $0.60 per M tokens)
- **Cascade Escalation:** If an initial fix by the cheap model fails unit tests, automatically escalates to the heavy model for subsequent repair iterations.
- **Results:** Achieves **-28.6% cost reduction** with **0% regression (100% pass rate)**.

Run: `python -m evaluation.runner.cli --multi-agent --model-routing --limit 3 --sandbox local`  
Compare: `python -m evaluation.experiments.compare evaluation/results/exp3_*.json evaluation/results/exp4_*.json`

## Tests

```bash
pytest -v
pytest tests/test_api.py -v
pytest tests/test_baseline_e2e.py -v  # builds a dummy repo and solves one issue
pytest tests/test_benchmark.py -v     # dataset validity (bugs fail pre-fix) + metrics math + 3-task mock run
pytest tests/test_retrieval.py -v     # AST + graph + hit@6 >=18/20 + Exp2 mini-mock with retrieval trace
pytest tests/test_multi_agent.py -v   # Phase 4 multi-agent sub-agent team & repair loop
pytest tests/test_router.py -v        # Phase 5 model router, complexity scoring & escalation
```
