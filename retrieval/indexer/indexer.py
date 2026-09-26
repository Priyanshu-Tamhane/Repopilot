from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from retrieval.ast.parser import FileEntities, parse_repo
from retrieval.embeddings.tfidf import TfIdfModel, build_tfidf
from retrieval.graph.dependencies import build_dependency_graph, build_test_mapping


@dataclass
class Chunk:
    id: str  # file::entity or file::chunk0
    file: str
    kind: str  # function | class | file
    name: str
    content: str
    start_line: int = 0
    end_line: int = 0


@dataclass
class RepoIndex:
    repo: str
    chunks: list[Chunk] = field(default_factory=list)
    tfidf: Optional[TfIdfModel] = None
    graph: dict[str, set[str]] = field(default_factory=dict)
    test_mapping: dict[str, list[str]] = field(default_factory=dict)
    parsed: dict[str, FileEntities] = field(default_factory=dict)


def _chunk_file(repo_root: Path, rel: str, fe: Optional[FileEntities]) -> list[Chunk]:
    p = repo_root / rel
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    chunks: list[Chunk] = []
    if fe and (fe.functions or fe.classes):
        for e in fe.functions:
            chunks.append(Chunk(id=f"{rel}::{e.name}:{e.lineno}", file=rel, kind="function", name=e.name, content=e.source or text, start_line=e.lineno, end_line=e.end_lineno))
        for e in fe.classes:
            chunks.append(Chunk(id=f"{rel}::{e.name}:{e.lineno}", file=rel, kind="class", name=e.name, content=e.source or text, start_line=e.lineno, end_line=e.end_lineno))
        # also a file-level chunk with header/imports for context
        if fe.imports:
            imp_text = "\n".join(f"import {i.name}" for i in fe.imports[:8])
            chunks.append(Chunk(id=f"{rel}::header", file=rel, kind="file", name=Path(rel).name, content=imp_text, start_line=1, end_line=1))
    else:
        # non-Python or unparseable: file-level chunk (truncate at 3000 chars)
        snippet = text[:3000]
        kind = "file"
        chunks.append(Chunk(id=f"{rel}::file", file=rel, kind=kind, name=Path(rel).name, content=snippet, start_line=1, end_line=len(snippet.splitlines())))
    return chunks


def build_index(repo_root: Path, save_path: Optional[Path] = None) -> RepoIndex:
    repo_root = repo_root.resolve()
    parsed = parse_repo(repo_root)
    graph = build_dependency_graph(parsed)
    test_mapping = build_test_mapping(repo_root, parsed)

    # collect files to chunk: all .py + .md/.txt for context (file-level)
    chunks: list[Chunk] = []
    for rel, fe in parsed.items():
        chunks.extend(_chunk_file(repo_root, rel, fe))
    # also include non-py docs as file chunks
    for p in repo_root.rglob("*"):
        if p.is_file() and p.suffix in (".md", ".txt", ".toml", ".json") and ".git" not in p.parts:
            rel = p.relative_to(repo_root).as_posix()
            if rel not in parsed:
                chunks.extend(_chunk_file(repo_root, rel, None))
    # dedup by id
    seen = set()
    uniq = []
    for c in chunks:
        if c.id not in seen:
            seen.add(c.id)
            uniq.append(c)
    chunks = uniq

    docs = [f"{c.file} {c.name} {c.content}" for c in chunks]
    tfidf = build_tfidf(docs) if docs else None

    idx = RepoIndex(repo=str(repo_root), chunks=chunks, tfidf=tfidf, graph=graph, test_mapping=test_mapping, parsed=parsed)
    if save_path:
        save_index(idx, Path(save_path))
    return idx


def save_index(idx: RepoIndex, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "repo": idx.repo,
        "chunks": [c.__dict__ for c in idx.chunks],
        "tfidf": {"vocab": idx.tfidf.vocab, "idf": idx.tfidf.idf, "doc_vectors": idx.tfidf.doc_vectors} if idx.tfidf else None,
        "graph": {k: sorted(v) for k, v in idx.graph.items()},
        "test_mapping": idx.test_mapping,
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_index(path: Path) -> RepoIndex:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    from retrieval.embeddings.tfidf import TfIdfModel as T

    tfidf = None
    if data.get("tfidf"):
        t = data["tfidf"]
        tfidf = T(vocab=t["vocab"], idf=t["idf"], doc_vectors=t["doc_vectors"], doc_norms=[1.0]*len(t["doc_vectors"]))
    chunks = [__import__("retrieval.indexer.indexer", fromlist=["Chunk"]).Chunk(**c) for c in data["chunks"]]
    graph = {k: set(v) for k, v in data.get("graph", {}).items()}
    return RepoIndex(repo=data["repo"], chunks=chunks, tfidf=tfidf, graph=graph, test_mapping=data.get("test_mapping", {}), parsed={})
