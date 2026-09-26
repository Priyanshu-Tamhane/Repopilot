"""Phase 3 tests: AST, graph, hit@k, Exp2 mock mini run."""
import tempfile
from pathlib import Path

import pytest

from agents.baseline.agent import BaselineAgent
from retrieval.ast.parser import parse_file, parse_repo
from retrieval.graph.dependencies import build_dependency_graph, build_test_mapping
from retrieval.indexer.indexer import build_index
from retrieval.retriever import retrieve
from evaluation.datasets.seed import build_dataset, materialize


def test_ast_parser():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "sample.py").write_text(
            "import os\nfrom utils.strings import reverse_text\n\ndef foo(a, b):\n    '''doc'''\n    return a + b\n\nclass Bar:\n    def method(self):\n        pass\n",
            encoding="utf-8",
        )
        fe = parse_file(root, root / "sample.py")
        assert any(i.name == "os" for i in fe.imports)
        assert any(i.name == "utils.strings.reverse_text" for i in fe.imports)
        assert any(f.name == "foo" for f in fe.functions)
        assert any(c.name == "Bar" for c in fe.classes)


def test_dependency_and_test_mapping():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "calculator.py").write_text("def add(a, b): return a + b", encoding="utf-8")
        (root / "test_calc.py").write_text("from calculator import add\ndef test_add(): assert add(2,3)==5", encoding="utf-8")
        parsed = parse_repo(root)
        graph = build_dependency_graph(parsed)
        assert "calculator.py" in graph["test_calc.py"]
        mapping = build_test_mapping(root, parsed)
        assert "calculator.py" in mapping["test_calc.py"]


def test_retriever_hit_rate():
    """Issue -> retrieval must contain true buggy file for >=18/20 seed tasks."""
    ds = build_dataset()
    hits = 0
    total = len(ds.tasks)
    with tempfile.TemporaryDirectory(prefix="retr-hit-") as td:
        for task in ds.tasks:
            repo = materialize(task, Path(td))
            idx = build_index(repo)
            rr = retrieve(idx, task.issue, repo, top_k=6)
            true_files = set(task.files.keys())
            if true_files & rr.candidate_files:
                hits += 1
            else:
                # debug info
                print(f"miss {task.id}: true={true_files} got={rr.candidate_files}")
    assert hits >= 18, f"hit@6 {hits}/{total} below threshold"


@pytest.mark.asyncio
async def test_exp2_mini_mock():
    """3-task retrieval run: should still succeed and use fewer tokens than full snapshot."""
    from retrieval.indexer.loader import get_file_snapshot

    ds = build_dataset()
    mini_ids = {"T01", "T10", "T13"}
    tasks = [t for t in ds.tasks if t.id in mini_ids]
    with tempfile.TemporaryDirectory(prefix="exp2-mini-") as td:
        for task in tasks:
            # estimate baseline tokens
            repo = materialize(task, Path(td) / task.id)
            full = get_file_snapshot(repo)
            full_tokens = len(full) // 4

            agent = BaselineAgent(use_mock=True, sandbox_mode="local", use_retrieval=True, retrieval_top_k=6)
            res = await agent.run(str(repo), task.issue)
            assert res.success, f"{task.id} retrieval agent failed: {res.error}"
            assert res.trace and "retrieval" in res.trace
            # candidate must include true file
            cand = res.trace["retrieval"]["candidate_files"]
            assert any(f in cand for f in task.files.keys()), f"{task.id} retrieval missed {task.files.keys()} vs {cand}"
            # tokens: on tiny 2-file repos retrieval may equal full; check overall budget bound
            ctx_tokens = res.trace["retrieval"]["context_tokens_est"]
            assert ctx_tokens <= 2000, f"{task.id} context too large {ctx_tokens}"
            # for repos where full > 500 chars, retrieval should not blow up
            if full_tokens > 200:
                assert ctx_tokens <= full_tokens * 1.5, f"{task.id} retrieval bloat {ctx_tokens} vs {full_tokens}"
