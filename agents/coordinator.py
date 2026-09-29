from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from agents.debugger import DebuggerAgent
from agents.implementer import ImplementerAgent
from agents.planner import PlannerAgent
from agents.protocol import SharedTaskState
from agents.researcher import ResearcherAgent
from agents.reviewer import ReviewerAgent
from agents.tester import TesterAgent
from api.schemas.tasks import TaskResponse
from execution.docker.sandbox import prepare_sandbox
from inference.models.base import LLMProvider
from inference.router.router import ModelRouter, ModelTier, RoutingDecision
from inference.telemetry.metrics import TaskTrace


class MultiAgentCoordinator:
    """Phase 4 & 5 Multi-Agent Coordinator.

    Orchestrates the collaborative team of 6 specialized agents:
      Planner -> Researcher -> [Implementer <-> Tester <-> Debugger] -> Reviewer

    Phase 5 adds:
      - Dynamic Model Routing: classifies task complexity and routes to CHEAP vs HEAVY LLM tier
      - Cascade Escalation: escalates to HEAVY tier if CHEAP tier fails tests during repair loop

    Maintains full signature parity with BaselineAgent.run() -> TaskResponse.
    """

    def __init__(
        self,
        workdir: str | None = None,
        sandbox_mode: str = "auto",
        use_mock: bool = True,
        model: str = "openai/gpt-oss-120b",
        api_key: str = "",
        provider: str = "mock",
        base_url: str = "https://api.groq.com/openai/v1",
        max_retries: int = 3,
        model_routing: bool = False,
        cheap_model: Optional[str] = None,
        heavy_model: Optional[str] = None,
    ):
        self.workdir = workdir
        self.sandbox_mode = sandbox_mode
        self.use_mock = use_mock
        self.model = model
        self.api_key = api_key
        self.provider_name = provider
        self.base_url = base_url
        self.max_retries = max_retries
        self.model_routing = model_routing
        self.cheap_model = cheap_model or ("mock-gpt-4o-mini-cheap" if use_mock else "openai/gpt-oss-20b")
        self.heavy_model = heavy_model or ("mock-gpt-4o-mini" if use_mock else model)

        self.router = ModelRouter(
            cheap_model=self.cheap_model,
            heavy_model=self.heavy_model,
            use_mock=self.use_mock,
        )

        self.provider: LLMProvider = self._make_provider_for_model(self.model)

        # Initialize the 6 sub-agents
        self.planner = PlannerAgent(self.provider)
        self.researcher = ResearcherAgent(self.provider)
        self.implementer = ImplementerAgent(self.provider)
        self.tester = TesterAgent(sandbox_mode=self.sandbox_mode)
        self.debugger = DebuggerAgent(self.provider)
        self.reviewer = ReviewerAgent(self.provider)

    def _make_provider_for_model(self, model_name: str) -> LLMProvider:
        if self.use_mock or not self.api_key:
            from inference.models.mock import MockLLMProvider

            return MockLLMProvider(model_name=model_name)
        if self.provider_name in ("groq", "llama", "mixtral", "gemma"):
            from inference.models.groq_provider import GroqProvider

            return GroqProvider(api_key=self.api_key, model=model_name, base_url=self.base_url)
        else:
            from inference.models.openai_provider import OpenAIProvider

            return OpenAIProvider(api_key=self.api_key, model=model_name)

    def _make_provider(self) -> LLMProvider:
        return self._make_provider_for_model(self.model)

    async def run(self, repository: str, issue: str) -> TaskResponse:
        start_time = time.time()
        sandbox = None

        try:
            # 1. Clone repository into isolated sandbox
            t0 = time.time()
            sandbox = prepare_sandbox(repository, workdir=self.workdir, mode=self.sandbox_mode)
            repo_path = sandbox.repo_path

            # Initialize shared state whiteboard
            trace = TaskTrace(task_id="multi_agent", repository=repository, issue=issue)
            trace.add_step("clone", (time.time() - t0) * 1000, detail=str(repo_path))

            state = SharedTaskState(
                repository=repository,
                issue=issue,
                repo_path=repo_path,
                sandbox_mode=self.sandbox_mode,
                use_mock=self.use_mock,
                max_retries=self.max_retries,
                trace=trace,
                tool_calls=1,  # clone step
            )

            # 2. Stage 1: Planning
            print(f"[Multi-Agent] 1/4 Planning strategy for issue: '{issue[:60]}...'")
            await self.planner.run(state)

            # 3. Stage 2: Codebase Research
            print(f"[Multi-Agent] 2/4 Researching repository files via AST & TF-IDF...")
            await self.researcher.run(state)

            # Dynamic Model Routing (Phase 5)
            routing_decision: Optional[RoutingDecision] = None
            if self.model_routing:
                routing_decision = self.router.route(
                    issue=state.issue,
                    context=state.research_context,
                    candidate_files=state.candidate_files,
                )
                print(
                    f"[Multi-Agent] Dynamic Model Routing -> {routing_decision.tier.value.upper()} tier "
                    f"({routing_decision.model_name}) | score={routing_decision.complexity_score:.2f}"
                )
                routed_provider = self._make_provider_for_model(routing_decision.model_name)
                self.implementer.provider = routed_provider
                self.debugger.provider = routed_provider
                state.trace.add_step("routing", 0, detail=routing_decision.reason)

            # 4. Stage 3: Implementation, Testing & Debugger Feedback Loop
            print(f"[Multi-Agent] 3/4 Implementation & self-correction loop (max {self.max_retries} retries)...")
            for iteration in range(1, self.max_retries + 1):
                state.iteration = iteration
                print(f"[Multi-Agent]   -> Iteration {iteration}: Applying code modifications...")
                await self.implementer.run(state)

                print(f"[Multi-Agent]   -> Iteration {iteration}: Running pytest in sandbox...")
                test_result = await self.tester.run(state)
                passed = test_result.get("passed", 0)
                failed = test_result.get("failed", 0)
                all_passed = test_result.get("all_passed", False)
                print(f"[Multi-Agent]   -> Results: {passed} passed, {failed} failed")

                if all_passed:
                    print(f"[Multi-Agent]   -> Tests passed successfully on iteration {iteration}!")
                    break

                if iteration < self.max_retries:
                    # Cascade Escalation: escalate to HEAVY tier on test failure if currently CHEAP
                    if (
                        self.model_routing
                        and routing_decision
                        and routing_decision.tier == ModelTier.CHEAP
                        and not routing_decision.escalated
                    ):
                        print(f"[Multi-Agent]   -> Escalating to HEAVY tier after test failure...")
                        routing_decision = self.router.escalate(
                            routing_decision,
                            failure_reason=test_result.get("output", "")[:100],
                        )
                        escalated_provider = self._make_provider_for_model(routing_decision.model_name)
                        self.implementer.provider = escalated_provider
                        self.debugger.provider = escalated_provider
                        state.trace.add_step("escalate", 0, detail=routing_decision.reason)

                    print(f"[Multi-Agent]   -> Tests failed. Invoking Debugger to diagnose...")
                    hint = await self.debugger.run(state)
                    print(f"[Multi-Agent]   -> Debugger advice: {hint[:100]}...")

            # 5. Stage 4: Code Review & Patch Verification
            print(f"[Multi-Agent] 4/4 Reviewing git diff patch and verifying safety invariants...")
            review_result = await self.reviewer.run(state)
            approved = review_result.get("approved", False)
            print(f"[Multi-Agent] Patch Approved: {approved} ({review_result.get('notes', '')})")

            duration = round(time.time() - start_time, 2)
            success = approved and (state.test_failed == 0 and (state.test_passed > 0 or bool(state.patch.strip())))

            state.trace.tool_calls = state.tool_calls
            td = state.trace.to_dict()
            td["multi_agent"] = {
                "iterations_used": state.iteration,
                "debug_rounds": len(state.debug_history),
                "approved": approved,
                "review_notes": state.review_notes,
                "candidate_files": state.candidate_files,
            }
            if routing_decision:
                td["routing"] = {
                    "initial_tier": "cheap" if routing_decision.escalated else routing_decision.tier.value,
                    "final_tier": routing_decision.tier.value,
                    "model_name": routing_decision.model_name,
                    "complexity_score": routing_decision.complexity_score,
                    "escalated": routing_decision.escalated,
                    "reason": routing_decision.reason,
                }

            return TaskResponse(
                success=success,
                patch=state.patch,
                tests_passed=state.test_passed,
                tests_failed=state.test_failed,
                duration_seconds=duration,
                input_tokens=state.input_tokens,
                output_tokens=state.output_tokens,
                llm_calls=state.llm_calls,
                tool_calls=state.tool_calls,
                estimated_cost=round(state.total_cost, 4),
                trace=td,
                error=None if success else f"Tests failed or review rejected: {state.test_output[:2000]}",
            )

        except Exception as e:
            import traceback

            duration = round(time.time() - start_time, 2)
            return TaskResponse(
                success=False,
                patch="",
                tests_passed=0,
                tests_failed=0,
                duration_seconds=duration,
                input_tokens=0,
                output_tokens=0,
                llm_calls=0,
                tool_calls=0,
                estimated_cost=0.0,
                error=f"{e}\n{traceback.format_exc()}",
            )
        finally:
            if sandbox is not None:
                try:
                    sandbox.cleanup()
                except Exception:
                    pass
