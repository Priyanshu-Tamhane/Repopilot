"""Run RepoPilot Phase 4 Multi-Agent System on a repository.

Usage:
  python run_multi_agent.py
  python run_multi_agent.py --repo path/to/repo --issue "Fix bug description"
  python run_multi_agent.py --real  # uses real Groq/OpenAI LLM from .env
"""
from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from agents.coordinator import MultiAgentCoordinator
from api.dependencies.config import get_settings


async def main():
    parser = argparse.ArgumentParser(description="Run RepoPilot Multi-Agent Coordinator")
    parser.add_argument(
        "--repo",
        default=str(Path(__file__).parent / "demo_repo"),
        help="Path or URL to the repository",
    )
    parser.add_argument(
        "--issue",
        default="Fix bug: add() in calculator.py returns wrong value for negative numbers",
        help="Bug report / issue text",
    )
    parser.add_argument(
        "--sandbox",
        default="auto",
        choices=["auto", "local", "docker"],
        help="Sandbox execution mode",
    )
    parser.add_argument(
        "--real",
        action="store_true",
        help="Use real Groq/OpenAI LLM instead of mock",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=3,
        help="Max repair retries for Debugger loop",
    )

    args = parser.parse_args()

    # Load settings from .env
    settings = get_settings()

    use_mock = not args.real if args.real else settings.llm_mock

    # Determine provider details
    if not use_mock and settings.groq_api_key:
        provider = "groq"
        model = settings.groq_model
        api_key = settings.groq_api_key
        base_url = settings.groq_base_url
    elif not use_mock and settings.openai_api_key:
        provider = "openai"
        model = settings.openai_model
        api_key = settings.openai_api_key
        base_url = "https://api.openai.com/v1"
    else:
        provider = "mock"
        model = "mock-gpt-4o-mini"
        api_key = ""
        base_url = ""
        use_mock = True

    print("=" * 65)
    print("REPOPILOT -- PHASE 4 MULTI-AGENT SYSTEM")
    print("=" * 65)
    print(f"Repository : {args.repo}")
    print(f"Issue      : {args.issue}")
    print(f"LLM Mode   : {'MOCK (Offline Heuristics)' if use_mock else f'REAL ({provider}: {model})'}")
    print(f"Sandbox    : {args.sandbox}")
    print(f"Max Retries: {args.retries}")
    print("-" * 65)

    coordinator = MultiAgentCoordinator(
        workdir=settings.workdir,
        sandbox_mode=args.sandbox,
        use_mock=use_mock,
        model=model,
        api_key=api_key,
        provider=provider,
        base_url=base_url,
        max_retries=args.retries,
    )

    result = await coordinator.run(args.repo, args.issue)

    print("\n" + "=" * 65)
    print(f"EXECUTION SUMMARY -- {'SUCCESS' if result.success else 'FAILED'}")
    print("=" * 65)
    print(f"Tests Passed     : {result.tests_passed}")
    print(f"Tests Failed     : {result.tests_failed}")
    print(f"Duration         : {result.duration_seconds}s")
    print(f"Tokens Used      : {result.input_tokens} in / {result.output_tokens} out")
    print(f"Estimated Cost   : ${result.estimated_cost:.4f}")
    print(f"LLM Invocations  : {result.llm_calls}")
    print(f"Tool Actions     : {result.tool_calls}")

    if result.trace and "multi_agent" in result.trace:
        ma = result.trace["multi_agent"]
        print(f"Iterations Used  : {ma.get('iterations_used')}")
        print(f"Debug Rounds     : {ma.get('debug_rounds')}")
        print(f"Review Decision  : {ma.get('review_notes')}")

    if result.patch.strip():
        print("\n" + "-" * 65)
        print("GENERATED GIT DIFF PATCH:")
        print("-" * 65)
        print(result.patch.strip())
    elif result.error:
        print("\n" + "-" * 65)
        print("ERROR DETAILS:")
        print("-" * 65)
        print(result.error)


if __name__ == "__main__":
    asyncio.run(main())
