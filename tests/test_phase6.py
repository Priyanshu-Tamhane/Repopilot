import asyncio
import tempfile
import time
from pathlib import Path

import pytest

from execution.workers.pool import WorkerPool
from execution.queue.manager import TaskManager
from inference.cache.cache import CachedLLMProvider, LLMCache
from inference.models.base import LLMResponse
from inference.models.mock import MockLLMProvider


@pytest.mark.asyncio
async def test_llm_cache_basic():
    cache = LLMCache(max_size=10, default_ttl=60.0)

    # Initial miss
    miss = await cache.get("model-a", "sys", "hello prompt")
    assert miss is None
    assert cache.misses == 1
    assert cache.hits == 0

    # Store
    resp = LLMResponse(
        content="hello response",
        input_tokens=100,
        output_tokens=50,
        model="model-a",
        latency_ms=200.0,
    )
    await cache.set("model-a", "sys", "hello prompt", resp, cost=0.005)

    # Hit
    hit = await cache.get("model-a", "sys", "hello prompt")
    assert hit is not None
    assert hit.content == "hello response"
    assert hit.input_tokens == 0  # 0 billed tokens on hit
    assert hit.output_tokens == 0
    assert cache.hits == 1
    assert cache.tokens_saved == 150
    assert cache.cost_saved == 0.005
    assert cache.hit_rate == 0.5  # 1 hit / 2 requests


@pytest.mark.asyncio
async def test_llm_cache_lru_eviction():
    cache = LLMCache(max_size=2)

    resp1 = LLMResponse(content="r1", input_tokens=10, output_tokens=10, model="m", latency_ms=10)
    resp2 = LLMResponse(content="r2", input_tokens=10, output_tokens=10, model="m", latency_ms=10)
    resp3 = LLMResponse(content="r3", input_tokens=10, output_tokens=10, model="m", latency_ms=10)

    await cache.set("m", "sys", "p1", resp1)
    await cache.set("m", "sys", "p2", resp2)
    assert len(cache._entries) == 2

    # Adding p3 should evict p1 (LRU)
    await cache.set("m", "sys", "p3", resp3)
    assert len(cache._entries) == 2
    assert await cache.get("m", "sys", "p1") is None
    assert await cache.get("m", "sys", "p2") is not None
    assert await cache.get("m", "sys", "p3") is not None


@pytest.mark.asyncio
async def test_cached_provider_wrapper():
    cache = LLMCache()
    mock_provider = MockLLMProvider()
    cached_provider = CachedLLMProvider(mock_provider, cache=cache)

    prompt = "FILE: math.py\nFix add(a, b)"
    r1 = await cached_provider.generate(prompt, system="sys")
    assert cache.hits == 0
    assert cache.misses == 1

    r2 = await cached_provider.generate(prompt, system="sys")
    assert cache.hits == 1
    assert "cached" in r2.model
    assert r2.content == r1.content


@pytest.mark.asyncio
async def test_worker_pool_concurrency():
    pool = WorkerPool(concurrency=2)

    async def _mock_task(val: int) -> int:
        await asyncio.sleep(0.05)
        return val * 2

    items = [1, 2, 3, 4]
    results = await pool.map(items, _mock_task)

    assert len(results) == 4
    vals = [r[0] for r in results]
    assert vals == [2, 4, 6, 8]

    stats = pool.stats()
    assert stats["completed_tasks"] == 4
    assert stats["peak_workers"] <= 2
    assert stats["avg_queue_latency_s"] >= 0.0


def _create_test_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "calculator.py").write_text(
        "def add(a, b):\n    if b < 0:\n        return a - b\n    return a + b\n",
        encoding="utf-8",
    )
    (repo / "test_calculator.py").write_text(
        "from calculator import add\n\n"
        "def test_add_positive():\n    assert add(2, 3) == 5\n\n"
        "def test_add_negative():\n    assert add(2, -3) == -1\n",
        encoding="utf-8",
    )
    import subprocess
    subprocess.run(["git", "init"], cwd=str(repo), capture_output=True)
    subprocess.run(["git", "add", "."], cwd=str(repo), capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=str(repo), capture_output=True)
    return repo


@pytest.mark.asyncio
async def test_task_manager_with_workers():
    with tempfile.TemporaryDirectory() as td:
        repo_dir = _create_test_repo(Path(td))
        manager = TaskManager(max_workers=2)

        result = await manager.submit(
            repository=str(repo_dir),
            issue="Fix add() in calculator.py: returns wrong value for negative numbers",
            agent_type="multi",
        )

        assert result.success is True
        assert result.trace is not None
        assert "queue_latency_s" in result.trace
        assert result.trace["queue_latency_s"] >= 0.0
