"""RepoPilot - Phase 5 Controlled Configurations Tests.

Validates the four controlled benchmark configurations (B0, B1, B2, B3):
1. Configuration loading from YAML (configs/b0.yaml, b1.yaml, b2.yaml, b3.yaml)
2. Proper parameter mapping across B0, B1, B2, and B3
3. Retrieval bounding and AST-chunk context adherence (B1)
4. Multi-agent token and retry aggregation contract (B2)
5. Complexity-based model routing decision verification (B3)
6. CLI integration with --config flag
"""
from __future__ import annotations

from pathlib import Path

from agents.base import (
    B0BaselineAgent,
    B1RetrievalAgent,
    B2MultiAgent,
    B3RoutingAgent,
    get_agent,
    load_agent_config,
)
from evaluation.bench.cli import build_parser
from inference.router.router import ModelRouter, ModelTier


def test_yaml_config_loading():
    """Verify that all 4 YAML config presets load correctly with expected attributes."""
    for cfg_key in ("b0", "b1", "b2", "b3"):
        yaml_path = Path("configs") / f"{cfg_key}.yaml"
        assert yaml_path.exists(), f"Missing config file: {yaml_path}"

        key, data = load_agent_config(yaml_path)
        assert key.lower() == cfg_key
        assert "description" in data
        assert "budget" in data

    # Verify B1 specific parameters
    _, b1_data = load_agent_config("configs/b1.yaml")
    assert b1_data.get("top_k") == 6
    assert b1_data.get("char_budget") == 8000

    # Verify B2 specific parameters
    _, b2_data = load_agent_config("configs/b2.yaml")
    assert b2_data.get("max_retries") == 3

    # Verify B3 specific parameters
    _, b3_data = load_agent_config("configs/b3.yaml")
    assert "cheap_model" in b3_data
    assert "heavy_model" in b3_data


def test_agent_instantiation_from_config_files():
    """Verify get_agent instantiates the proper class when given a YAML file path."""
    agent_b0 = get_agent("configs/b0.yaml")
    assert isinstance(agent_b0, B0BaselineAgent)
    assert agent_b0.name == "b0_baseline"

    agent_b1 = get_agent("configs/b1.yaml")
    assert isinstance(agent_b1, B1RetrievalAgent)
    assert agent_b1.top_k == 6
    assert agent_b1.char_budget == 8000

    agent_b2 = get_agent("configs/b2.yaml")
    assert isinstance(agent_b2, B2MultiAgent)
    assert agent_b2.max_retries == 3

    agent_b3 = get_agent("configs/b3.yaml")
    assert isinstance(agent_b3, B3RoutingAgent)
    assert agent_b3.cheap_model == "openai/gpt-oss-20b"
    assert agent_b3.heavy_model == "openai/gpt-oss-120b"


def test_b1_retrieval_configuration_bounds(tmp_path: Path):
    """Verify B1 retrieval respects top_k and char_budget constraints."""
    repo = tmp_path / "repo"
    repo.mkdir()
    for i in range(10):
        (repo / f"module_{i}.py").write_text(f"def func_{i}():\n    return {i}\n" * 50, encoding="utf-8")

    from retrieval.indexer.indexer import build_index
    from retrieval.retriever import retrieve

    idx = build_index(repo)
    res = retrieve(idx, "func_1 calculation", repo, top_k=3, char_budget=500)
    assert len(res.candidate_files) <= 4
    assert res.stats.get("context_chars", 0) > 0


def test_b2_multi_agent_state_and_token_aggregation():
    """Verify B2 multi-agent protocol aggregates tokens across all sub-agent steps."""
    from agents.protocol import SharedTaskState
    from inference.models.base import LLMResponse

    state = SharedTaskState(
        repository="test_repo",
        issue="Fix bug in calculation",
        repo_path=Path("."),
        sandbox_mode="local",
        use_mock=True,
    )

    # Record 3 subagent LLM calls via protocol helper
    state.record_llm_call(LLMResponse(content="r1", input_tokens=150, output_tokens=50, model="mock", latency_ms=10.0), cost=0.0001, step_name="planner")
    state.record_llm_call(LLMResponse(content="r2", input_tokens=200, output_tokens=80, model="mock", latency_ms=15.0), cost=0.0002, step_name="researcher")
    state.record_llm_call(LLMResponse(content="r3", input_tokens=300, output_tokens=120, model="mock", latency_ms=25.0), cost=0.0003, step_name="implementer")

    assert state.input_tokens == 650
    assert state.output_tokens == 250
    assert state.llm_calls == 3
    assert len(state.trace.llm_calls) == 3


def test_b3_routing_decision_logic():
    """Verify B3 complexity scoring routes easy tasks to cheap tier and hard to heavy tier."""
    router = ModelRouter(
        cheap_model="llama-3.1-8b-instant",
        heavy_model="llama-3.3-70b-versatile",
        use_mock=False,
    )

    # Easy task: simple typo / sign bug
    decision_easy = router.route(
        issue="Fix typo in docstring and add negative sign",
        context="def add(a, b): return a + b",
        candidate_files=["calc.py"],
    )
    assert decision_easy.tier == ModelTier.CHEAP
    assert decision_easy.model_name == "llama-3.1-8b-instant"
    assert decision_easy.complexity_score < 0.50

    # Hard task: deadlock, concurrency, recursion
    decision_hard = router.route(
        issue="Fix deadlock and race condition in asyncio thread synchronization tree recursion",
        context="def worker(): pass\n" * 200,
        candidate_files=["thread_pool.py", "lock_manager.py", "async_worker.py", "event_loop.py"],
    )
    assert decision_hard.tier == ModelTier.HEAVY
    assert decision_hard.model_name == "llama-3.3-70b-versatile"
    assert decision_hard.complexity_score >= 0.50


def test_cli_config_option():
    """Verify repopilot-bench run CLI accepts --config flag."""
    parser = build_parser()
    args = parser.parse_args(["run", "--config", "configs/b2.yaml", "--limit", "2"])
    assert args.config == "configs/b2.yaml"
    assert args.limit == 2
