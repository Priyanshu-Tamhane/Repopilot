"""RepoPilot - Common Benchmark Agent Interface (Phase 4).

Standardizes all agent configurations (B0 Baseline, B1 Retrieval, B2 Multi-Agent, B3 Routing)
behind a uniform contract:
    agent.solve(task: BenchmarkTask, workspace: Path, budget: TaskBudget) -> AgentOutput

The benchmark runner controls workspace creation, budget enforcement,
and external clean-room evaluation.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from dataset.schema import BenchmarkTask
from execution.docker.sandbox import get_git_patch
from inference.models.base import LLMProvider
from retrieval.indexer.loader import get_file_snapshot


@dataclass
class TaskBudget:
    """Resource constraints for benchmark execution (Spec §12)."""
    max_wall_time_s: float = 300.0
    max_llm_calls: int = 20
    max_tokens: int = 100_000
    max_tool_calls: int = 30
    max_retries: int = 3


@dataclass
class AgentOutput:
    """Canonical agent output contract (Spec §2 & Phase 4)."""
    patch: str
    input_tokens: int = 0
    output_tokens: int = 0
    llm_calls: int = 0
    tool_calls: int = 0
    retries: int = 0
    duration_seconds: float = 0.0
    model: str = ""
    provider: str = ""
    trace: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


class BaseBenchmarkAgent(ABC):
    """Abstract base class for all benchmark agent configurations."""

    def __init__(
        self,
        name: str,
        model: str = "openai/gpt-oss-120b",
        provider: str = "mock",
        use_mock: bool = True,
        api_key: str = "",
        base_url: str = "https://api.groq.com/openai/v1",
        **kwargs: Any,
    ) -> None:
        self.name = name
        self.model = model
        self.provider = provider
        self.use_mock = use_mock
        self.api_key = api_key
        self.base_url = base_url
        self.kwargs = kwargs

    def _make_provider(self, model_name: Optional[str] = None) -> LLMProvider:
        m = model_name or self.model
        if self.use_mock or not self.api_key:
            from inference.models.mock import MockLLMProvider
            return MockLLMProvider(model_name=m)
        if self.provider in ("groq", "llama", "mixtral", "gemma"):
            from inference.models.groq_provider import GroqProvider
            return GroqProvider(api_key=self.api_key, model=m, base_url=self.base_url)
        from inference.models.openai_provider import OpenAIProvider
        return OpenAIProvider(api_key=self.api_key, model=m)

    @abstractmethod
    async def solve(self, task: BenchmarkTask, workspace: Path, budget: TaskBudget) -> AgentOutput:
        """Solve task in workspace and return AgentOutput."""
        pass


class B0BaselineAgent(BaseBenchmarkAgent):
    """B0 — Naive Baseline: Full repository snapshot, single LLM step, no RAG."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(name="b0_baseline", **kwargs)

    async def solve(self, task: BenchmarkTask, workspace: Path, budget: TaskBudget) -> AgentOutput:
        start_time = time.time()
        tool_calls = 0
        llm_calls = 0
        input_tokens = 0
        output_tokens = 0

        try:
            snapshot = get_file_snapshot(workspace)
            tool_calls += 1

            from agents.baseline.agent import SYSTEM_PROMPT, _build_prompt
            prompt = _build_prompt(task.issue_description, snapshot)

            if (time.time() - start_time) > budget.max_wall_time_s:
                return AgentOutput(
                    patch="",
                    duration_seconds=time.time() - start_time,
                    error="BudgetExceeded: Wall time expired before LLM call",
                )

            llm = self._make_provider()
            resp = await llm.generate(prompt=prompt, system=SYSTEM_PROMPT)
            llm_calls += 1
            input_tokens += resp.input_tokens
            output_tokens += resp.output_tokens

            from agents.baseline.agent import BaselineAgent
            agent_helper = BaselineAgent(use_mock=self.use_mock)
            edits = agent_helper._apply_edits(workspace, resp.content, task.issue_description, snapshot)
            tool_calls += len(edits)

            patch = get_git_patch(workspace)
            tool_calls += 1

            return AgentOutput(
                patch=patch,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                llm_calls=llm_calls,
                tool_calls=tool_calls,
                duration_seconds=time.time() - start_time,
                model=self.model,
                provider=self.provider,
                trace={"config": "b0_baseline", "edits_count": len(edits)},
            )
        except Exception as e:
            return AgentOutput(
                patch="",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                llm_calls=llm_calls,
                tool_calls=tool_calls,
                duration_seconds=time.time() - start_time,
                model=self.model,
                provider=self.provider,
                error=str(e),
            )


class B1RetrievalAgent(BaseBenchmarkAgent):
    """B1 — Retrieval: AST + TF-IDF file ranking, top-6 files, 8k context window."""

    def __init__(self, top_k: int = 6, char_budget: int = 8000, **kwargs: Any) -> None:
        super().__init__(name="b1_retrieval", **kwargs)
        self.top_k = top_k
        self.char_budget = char_budget

    async def solve(self, task: BenchmarkTask, workspace: Path, budget: TaskBudget) -> AgentOutput:
        start_time = time.time()
        tool_calls = 0
        llm_calls = 0
        input_tokens = 0
        output_tokens = 0

        try:
            from retrieval.retriever import retrieve
            from retrieval.indexer.indexer import build_index
            from agents.baseline.agent import BaselineAgent, SYSTEM_PROMPT, _build_prompt

            # 1. Index & Retrieve
            idx = build_index(workspace)
            rr = retrieve(idx, task.issue_description, workspace, top_k=self.top_k, char_budget=self.char_budget)
            tool_calls += 2

            # 2. Build targeted prompt
            prompt = _build_prompt(task.issue_description, rr.context)

            # 3. LLM Call
            llm = self._make_provider()
            resp = await llm.generate(prompt=prompt, system=SYSTEM_PROMPT)
            llm_calls += 1
            input_tokens += resp.input_tokens
            output_tokens += resp.output_tokens

            # 4. Parse & apply edits
            agent_helper = BaselineAgent(use_mock=self.use_mock)
            edits = agent_helper._apply_edits(workspace, resp.content, task.issue_description, rr.context)
            tool_calls += len(edits)

            # 5. Extract git patch
            patch = get_git_patch(workspace)
            tool_calls += 1

            return AgentOutput(
                patch=patch,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                llm_calls=llm_calls,
                tool_calls=tool_calls,
                duration_seconds=time.time() - start_time,
                model=self.model,
                provider=self.provider,
                trace={
                    "config": "b1_retrieval",
                    "candidate_files": rr.stats.get("candidate_files", []),
                    "context_chars": rr.stats.get("context_chars", 0),
                    "edits_count": len(edits),
                },
            )
        except Exception as e:
            return AgentOutput(
                patch="",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                llm_calls=llm_calls,
                tool_calls=tool_calls,
                duration_seconds=time.time() - start_time,
                model=self.model,
                provider=self.provider,
                error=str(e),
            )


class B2MultiAgent(BaseBenchmarkAgent):
    """B2 — Multi-Agent: Explicit roles (Planner, Researcher, Implementer, Debugger, Reviewer)."""

    def __init__(self, max_retries: int = 3, **kwargs: Any) -> None:
        super().__init__(name="b2_multi_agent", **kwargs)
        self.max_retries = max_retries

    async def solve(self, task: BenchmarkTask, workspace: Path, budget: TaskBudget) -> AgentOutput:
        start_time = time.time()
        from agents.protocol import SharedTaskState
        from agents.planner import PlannerAgent
        from agents.researcher import ResearcherAgent
        from agents.implementer import ImplementerAgent
        from agents.tester import TesterAgent
        from agents.debugger import DebuggerAgent
        from agents.reviewer import ReviewerAgent

        llm = self._make_provider()
        state = SharedTaskState(
            repository=str(workspace),
            issue=task.issue_description,
            repo_path=workspace,
            sandbox_mode="local",
            use_mock=self.use_mock,
            max_retries=min(self.max_retries, budget.max_retries),
        )

        try:
            # 1. Planner
            planner = PlannerAgent(llm)
            await planner.run(state)

            # 2. Researcher
            researcher = ResearcherAgent(llm)
            await researcher.run(state)

            # 3. Implementer
            implementer = ImplementerAgent(llm)
            await implementer.run(state)

            # 4. Tester + Debugger loop
            tester = TesterAgent()
            debugger = DebuggerAgent(llm)
            for _ in range(state.max_retries):
                await tester.run(state)
                if state.test_failed == 0 and state.test_passed > 0:
                    break
                # Debug iteration
                await debugger.run(state)
                await implementer.run(state)

            # 5. Reviewer
            reviewer = ReviewerAgent(llm)
            await reviewer.run(state)

            patch = state.patch or get_git_patch(workspace)
            input_tokens = sum(c.input_tokens for c in state.llm_calls)
            output_tokens = sum(c.output_tokens for c in state.llm_calls)

            return AgentOutput(
                patch=patch,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                llm_calls=len(state.llm_calls),
                tool_calls=state.tool_calls,
                retries=state.iteration,
                duration_seconds=time.time() - start_time,
                model=self.model,
                provider=self.provider,
                trace={"config": "b2_multi_agent", "plan": state.plan, "approved": state.approved},
            )
        except Exception as e:
            return AgentOutput(
                patch="",
                duration_seconds=time.time() - start_time,
                model=self.model,
                provider=self.provider,
                error=str(e),
            )


class B3RoutingAgent(BaseBenchmarkAgent):
    """B3 — Model Routing: Cost/complexity tiering between cheap and heavy models."""

    def __init__(
        self,
        cheap_model: str = "openai/gpt-oss-20b",
        heavy_model: str = "openai/gpt-oss-120b",
        **kwargs: Any,
    ) -> None:
        super().__init__(name="b3_routing", model=heavy_model, **kwargs)
        self.cheap_model = cheap_model
        self.heavy_model = heavy_model

    async def solve(self, task: BenchmarkTask, workspace: Path, budget: TaskBudget) -> AgentOutput:
        start_time = time.time()
        from inference.router.router import ModelRouter
        from retrieval.retriever import retrieve
        from retrieval.indexer.indexer import build_index
        from agents.baseline.agent import BaselineAgent, SYSTEM_PROMPT, _build_prompt

        router = ModelRouter(
            cheap_model=self.cheap_model,
            heavy_model=self.heavy_model,
            use_mock=self.use_mock,
        )

        tool_calls = 0
        llm_calls = 0
        input_tokens = 0
        output_tokens = 0

        try:
            # 1. Retrieve candidate files for context
            idx = build_index(workspace)
            rr = retrieve(idx, task.issue_description, workspace, top_k=6, char_budget=8000)
            tool_calls += 2

            # 2. Route task complexity
            route_decision = router.route(
                issue=task.issue_description,
                context=rr.context,
                candidate_files=rr.stats.get("candidate_files", []),
            )
            selected_model = route_decision.selected_model
            tier_name = route_decision.tier.value

            # 3. LLM call with routed model
            llm = self._make_provider(model_name=selected_model)
            prompt = _build_prompt(task.issue_description, rr.context)
            resp = await llm.generate(prompt=prompt, system=SYSTEM_PROMPT)
            llm_calls += 1
            input_tokens += resp.input_tokens
            output_tokens += resp.output_tokens

            # 4. Apply edits
            agent_helper = BaselineAgent(use_mock=self.use_mock)
            edits = agent_helper._apply_edits(workspace, resp.content, task.issue_description, rr.context)
            tool_calls += len(edits)

            patch = get_git_patch(workspace)
            tool_calls += 1

            return AgentOutput(
                patch=patch,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                llm_calls=llm_calls,
                tool_calls=tool_calls,
                duration_seconds=time.time() - start_time,
                model=selected_model,
                provider=self.provider,
                trace={
                    "config": "b3_routing",
                    "routing": {
                        "tier": tier_name,
                        "selected_model": selected_model,
                        "complexity_score": route_decision.complexity_score,
                        "reasons": route_decision.reasons,
                    },
                },
            )
        except Exception as e:
            return AgentOutput(
                patch="",
                duration_seconds=time.time() - start_time,
                model=self.model,
                provider=self.provider,
                error=str(e),
            )


def get_agent(config: str, **kwargs: Any) -> BaseBenchmarkAgent:
    """Factory to instantiate benchmark agent by configuration key."""
    cfg = config.lower().strip()
    if cfg in ("b0", "b0_baseline", "baseline"):
        return B0BaselineAgent(**kwargs)
    elif cfg in ("b1", "b1_retrieval", "retrieval", "rag"):
        return B1RetrievalAgent(**kwargs)
    elif cfg in ("b2", "b2_multi_agent", "multi", "multi_agent"):
        return B2MultiAgent(**kwargs)
    elif cfg in ("b3", "b3_routing", "routing"):
        return B3RoutingAgent(**kwargs)
    raise ValueError(f"Unknown agent configuration '{config}'. Choose from: b0, b1, b2, b3")
