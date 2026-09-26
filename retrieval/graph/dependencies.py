from __future__ import annotations

from pathlib import Path
from typing import Dict, Set

from retrieval.ast.parser import FileEntities, parse_repo


def _normalize_import(imp: str) -> str:
    # from a.b import c -> a.b.c already normalized; keep first segment for file matching
    return imp.split(".")[0].lower()


def build_dependency_graph(parsed: Dict[str, FileEntities]) -> Dict[str, Set[str]]:
    """file -> set(imported file rel paths) for files with resolvable local imports."""
    # map module stem -> rel path candidates
    stem_to_paths: Dict[str, list[str]] = {}
    for rel in parsed.keys():
        stem = Path(rel).stem.lower()
        stem_to_paths.setdefault(stem, []).append(rel)
        # also package qualified: pkg/ops.py -> ops
        pkg = Path(rel).parent.as_posix().lower()
        if pkg and pkg != ".":
            stem_to_paths.setdefault(Path(rel).name.lower(), []).append(rel)

    graph: Dict[str, Set[str]] = {rel: set() for rel in parsed}
    for rel, fe in parsed.items():
        for imp in fe.imports:
            key = _normalize_import(imp.name)
            for cand in stem_to_paths.get(key, []):
                if cand != rel:
                    graph[rel].add(cand)
            # handle full path like utils.strings
            full = imp.name.lower().replace(".", "/")
            for cand_rel in parsed.keys():
                cand_no_ext = cand_rel[:-3] if cand_rel.endswith(".py") else cand_rel
                if cand_no_ext.lower() == full or cand_no_ext.lower().endswith("/" + full):
                    if cand_rel != rel:
                        graph[rel].add(cand_rel)
    return graph


def build_test_mapping(repo_root: Path, parsed: Dict[str, FileEntities]) -> Dict[str, list[str]]:
    """test file -> list(source files it likely tests) via imports + naming convention."""
    test_files = [rel for rel in parsed.keys() if _is_test_path(rel)]
    source_files = [rel for rel in parsed.keys() if not _is_test_path(rel)]
    mapping: Dict[str, list[str]] = {}
    graph = build_dependency_graph(parsed)
    for trel in test_files:
        linked: Set[str] = set(graph.get(trel, set()))
        # heuristic: test_foo.py -> foo.py , foo_test.py -> foo.py
        stem = Path(trel).stem.lower()
        for prefix in ("test_",):
            if stem.startswith(prefix):
                cand = stem[len(prefix):]
                for s in source_files:
                    if Path(s).stem.lower() == cand:
                        linked.add(s)
        if stem.endswith("_test"):
            cand = stem[:-5]
            for s in source_files:
                if Path(s).stem.lower() == cand:
                    linked.add(s)
        # also utils/strings.py -> test_strings.py
        linked_sorted = sorted(linked)
        mapping[trel] = linked_sorted if linked_sorted else []
    return mapping


def _is_test_path(path: str) -> bool:
    parts = path.replace("\\", "/").split("/")
    name = parts[-1].lower()
    if name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py":
        return True
    return any(p.lower() in ("tests", "test") for p in parts[:-1])


def find_relevant_tests(
    candidate_sources: Set[str],
    test_mapping: Dict[str, list[str]],
    all_test_files: list[str],
) -> list[str]:
    """Return test files that map to any of candidate_sources (ordered deterministically)."""
    out = []
    for tfile, sources in test_mapping.items():
        if any(s in candidate_sources for s in sources):
            out.append(tfile)
    # fallback: if no mapping hit, include all tests that import candidate filename stem
    if not out and candidate_sources:
        stems = {Path(s).stem.lower() for s in candidate_sources}
        for tfile in all_test_files:
            stem = Path(tfile).stem.lower().replace("test_", "")
            if stem in stems:
                out.append(tfile)
    return sorted(set(out))
