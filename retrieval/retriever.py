from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from retrieval.embeddings.tfidf import cosine_sparse, embed_query
from retrieval.graph.dependencies import find_relevant_tests
from retrieval.indexer.indexer import Chunk, RepoIndex, build_index


@dataclass
class RetrievalResult:
    chunks: list[Chunk]
    scores: list[float]
    candidate_files: set[str]
    relevant_tests: list[str]
    context: str
    stats: dict


def retrieve(
    index: RepoIndex,
    query: str,
    repo_root: Path,
    top_k: int = 6,
    expand: bool = True,
    include_tests: bool = True,
    char_budget: int = 8000,
) -> RetrievalResult:
    # rank chunks
    if not index.tfidf or not index.chunks:
        return RetrievalResult([], [], set(), [], "", {"ranked": 0, "top_k": 0, "expanded": 0})

    qvec = embed_query(query, index.tfidf)
    scored = []
    for i, dvec in enumerate(index.tfidf.doc_vectors):
        s = cosine_sparse(qvec, dvec)
        # small boost for filename match
        ch = index.chunks[i]
        q_lower = query.lower()
        if Path(ch.file).stem.lower() in q_lower or Path(ch.file).name.lower() in q_lower:
            s += 0.15
        # boost if func name appears in query
        if ch.name.lower() in q_lower:
            s += 0.10
        scored.append((s, i))
    scored.sort(reverse=True, key=lambda x: x[0])

    top_idx = [i for s, i in scored[:top_k] if s > 0]
    # fallback: if all zero, take top_k anyway (ensures recall on tiny repos)
    if not top_idx:
        top_idx = [i for _, i in scored[:top_k]]

    candidate_files: set[str] = {index.chunks[i].file for i in top_idx}
    # 1-hop expansion via import graph
    if expand:
        for f in list(candidate_files):
            for dep in index.graph.get(f, set()):
                candidate_files.add(dep)

    relevant_tests: list[str] = []
    if include_tests:
        all_tests = [rel for rel in index.parsed.keys() if rel not in candidate_files and (rel.startswith("test_") or "/test_" in rel or rel.startswith("tests/"))]
        # also include from test_mapping keys
        all_tests = sorted(set(all_tests) | set(index.test_mapping.keys()))
        relevant_tests = find_relevant_tests(candidate_files, index.test_mapping, all_tests)

    # assemble context: full file contents for candidate files, ranked chunks otherwise
    context_parts: list[str] = []
    budget = char_budget
    # Prefer full file for candidate sources (better for LLM to write full file)
    for f in sorted(candidate_files):
        p = repo_root / f
        if p.exists():
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                text = ""
            block = f"FILE: {f}\n```\n{text[:6000]}\n```"
            if len(block) > budget and context_parts:
                break
            context_parts.append(block)
            budget -= len(block)
            if budget <= 0:
                break
    # Append relevant tests (truncated)
    for tfile in relevant_tests:
        p = repo_root / tfile
        if p.exists() and budget > 500:
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")[:2000]
            except Exception:
                continue
            block = f"FILE: {tfile} (relevant test)\n```\n{text}\n```"
            if len(block) > budget:
                continue
            context_parts.append(block)
            budget -= len(block)

    context = "\n\n".join(context_parts)
    # stats
    scores = [s for s, _ in scored if s > 0][:top_k]
    stats = {
        "ranked": len(index.chunks),
        "top_k": len(top_idx),
        "candidate_files": sorted(candidate_files),
        "relevant_tests": relevant_tests,
        "expanded": len(candidate_files) - len({index.chunks[i].file for i in top_idx}),
        "context_chars": len(context),
    }
    chunks = [index.chunks[i] for i in top_idx]
    top_scores = [s for s, _ in scored[:len(chunks)]]
    return RetrievalResult(chunks=chunks, scores=top_scores, candidate_files=candidate_files, relevant_tests=relevant_tests, context=context, stats=stats)


def build_retrieval_context(repo_root: Path, issue: str, char_budget: int = 8000) -> tuple[str, RetrievalResult, RepoIndex]:
    idx = build_index(repo_root)
    res = retrieve(idx, issue, repo_root, char_budget=char_budget)
    return res.context, res, idx
