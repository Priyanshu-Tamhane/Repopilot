"""RepoPilot - Standardized Benchmark Harness (Phase 4).

Coordinates end-to-end benchmark execution:
1. Workspace initialization at exact base_commit
2. Agent execution behind canonical BaseBenchmarkAgent interface
3. Strict TaskBudget timeout & resource monitoring
4. Independent external clean-room evaluation (CleanRoomEvaluator)
5. Comprehensive Per-Run JSON persistence without secrets
"""
from __future__ import annotations

import asyncio
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import List, Optional

from agents.base import BaseBenchmarkAgent, TaskBudget, get_agent
from dataset.schema import BenchmarkTask, load_tasks_jsonl
from evaluation.bench.schema import BenchmarkRunRecord, EvaluationSummary
from execution.docker.evaluator import CleanRoomEvaluator


class BenchmarkHarness:
    """Standardized Benchmark Harness for controlled agent evaluation."""

    def __init__(
        self,
        agent_config: str = "b0",
        model: str = "openai/gpt-oss-120b",
        provider: str = "mock",
        use_mock: bool = True,
        api_key: str = "",
        base_url: str = "https://api.groq.com/openai/v1",
        budget: Optional[TaskBudget] = None,
        workdir: Optional[Path] = None,
        out_dir: Optional[Path] = None,
    ) -> None:
        self.agent_config = agent_config
        self.model = model
        self.provider = provider
        self.use_mock = use_mock
        self.api_key = api_key
        self.base_url = base_url
        self.budget = budget or TaskBudget()
        self.workdir = workdir or Path(tempfile.gettempdir()) / "repopilot_harness"
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.out_dir = out_dir or Path("evaluation/results")
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.evaluator = CleanRoomEvaluator(workdir=self.workdir / "eval_cleanroom", timeout_s=int(self.budget.max_wall_time_s))

    def _prepare_agent_workspace(self, task: BenchmarkTask, run_id: str) -> Path:
        """Create isolated workspace checkout at task.base_commit."""
        ws_dir = self.workdir / f"ws_{task.task_id}_{run_id}"
        if ws_dir.exists():
            shutil.rmtree(ws_dir, ignore_errors=True)
        ws_dir.mkdir(parents=True, exist_ok=True)

        repo_source = task.repository
        if Path(repo_source).exists():
            # Local directory copy
            shutil.copytree(str(Path(repo_source).resolve()), str(ws_dir), dirs_exist_ok=True)
            r = subprocess.run(["git", "status"], cwd=str(ws_dir), capture_output=True, text=True)
        else:
            # Remote clone
            r = subprocess.run(["git", "clone", "--filter=blob:none", repo_source, str(ws_dir)], capture_output=True, text=True)

        if r.returncode != 0:
            raise RuntimeError(f"Failed to clone repository {repo_source}: {r.stderr}")

        # Pinned base commit checkout
        r_co = subprocess.run(["git", "checkout", "-f", task.base_commit], cwd=str(ws_dir), capture_output=True, text=True)
        if r_co.returncode != 0:
            raise RuntimeError(f"Failed to checkout base_commit {task.base_commit}: {r_co.stderr}")

        return ws_dir

    async def run_task(self, task: BenchmarkTask, agent: Optional[BaseBenchmarkAgent] = None) -> BenchmarkRunRecord:
        """Run a single task attempt through the standardized lifecycle."""
        run_id = str(uuid.uuid4())[:8]
        start_time = time.time()

        if agent is None:
            agent = get_agent(
                config=self.agent_config,
                model=self.model,
                provider=self.provider,
                use_mock=self.use_mock,
                api_key=self.api_key,
                base_url=self.base_url,
            )

        workspace = None
        try:
            # 1. Setup isolated workspace
            workspace = self._prepare_agent_workspace(task, run_id)

            # 2. Execute agent with budget timeout
            try:
                agent_output = await asyncio.wait_for(
                    agent.solve(task, workspace, self.budget),
                    timeout=self.budget.max_wall_time_s,
                )
            except asyncio.TimeoutError:
                eval_summary = EvaluationSummary(
                    resolved=False,
                    failure_category="timeout",
                    error=f"Task timed out after {self.budget.max_wall_time_s}s limit",
                )
                record = BenchmarkRunRecord.create(
                    run_id=run_id,
                    task_id=task.task_id,
                    agent_config=agent.name,
                    model_id=self.model,
                    provider=self.provider,
                    base_commit=task.base_commit,
                    duration_seconds=time.time() - start_time,
                    input_tokens=0,
                    output_tokens=0,
                    tool_calls=0,
                    retries=0,
                    patch="",
                    evaluation=eval_summary,
                    diagnostic_notes="Wall time budget exceeded",
                )
                record.save(self.out_dir)
                return record

            # 3. Independent external evaluation
            eval_res = self.evaluator.evaluate(task, agent_output.patch)

            eval_summary = EvaluationSummary(
                resolved=eval_res.success,
                tests_passed=eval_res.tests_passed,
                tests_failed=eval_res.tests_failed,
                failure_category=eval_res.failure_category,
                error=eval_res.error,
                output_preview=(eval_res.output or "")[:2000],
            )

            # 4. Create persistent record
            record = BenchmarkRunRecord.create(
                run_id=run_id,
                task_id=task.task_id,
                agent_config=agent.name,
                model_id=agent_output.model or self.model,
                provider=agent_output.provider or self.provider,
                base_commit=task.base_commit,
                duration_seconds=time.time() - start_time,
                input_tokens=agent_output.input_tokens,
                output_tokens=agent_output.output_tokens,
                tool_calls=agent_output.tool_calls,
                retries=agent_output.retries,
                patch=agent_output.patch,
                evaluation=eval_summary,
                diagnostic_notes=agent_output.error or "",
                trace=agent_output.trace,
            )

            record.save(self.out_dir)
            return record

        except Exception as e:
            eval_summary = EvaluationSummary(
                resolved=False,
                failure_category="harness_error",
                error=str(e),
            )
            record = BenchmarkRunRecord.create(
                run_id=run_id,
                task_id=task.task_id,
                agent_config=agent.name if agent else self.agent_config,
                model_id=self.model,
                provider=self.provider,
                base_commit=task.base_commit,
                duration_seconds=time.time() - start_time,
                input_tokens=0,
                output_tokens=0,
                tool_calls=0,
                retries=0,
                patch="",
                evaluation=eval_summary,
                diagnostic_notes=f"Harness exception: {e}",
            )
            record.save(self.out_dir)
            return record

        finally:
            # 5. Clean up agent workspace
            if workspace and workspace.exists():
                shutil.rmtree(workspace, ignore_errors=True)

    async def run_benchmark(
        self,
        dataset_path: Path | str = "dataset/tasks.jsonl",
        limit: Optional[int] = None,
    ) -> List[BenchmarkRunRecord]:
        """Run full benchmark dataset sequentially and return list of records."""
        tasks = load_tasks_jsonl(dataset_path)
        if limit:
            tasks = tasks[:limit]

        records: List[BenchmarkRunRecord] = []
        agent = get_agent(
            config=self.agent_config,
            model=self.model,
            provider=self.provider,
            use_mock=self.use_mock,
            api_key=self.api_key,
            base_url=self.base_url,
        )

        for i, task in enumerate(tasks, 1):
            rec = await self.run_task(task, agent=agent)
            records.append(rec)

        return records
