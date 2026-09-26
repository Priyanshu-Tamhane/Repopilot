from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class CodeEntity:
    kind: str  # function | class | import
    name: str
    file: str  # rel posix
    lineno: int
    end_lineno: int
    docstring: Optional[str] = None
    source: str = ""


@dataclass
class FileEntities:
    path: str
    imports: list[CodeEntity] = field(default_factory=list)
    functions: list[CodeEntity] = field(default_factory=list)
    classes: list[CodeEntity] = field(default_factory=list)

    @property
    def all(self) -> list[CodeEntity]:
        return self.imports + self.functions + self.classes


def parse_file(repo_root: Path, file_path: Path) -> FileEntities:
    rel = file_path.relative_to(repo_root).as_posix()
    try:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return FileEntities(path=rel)
    try:
        tree = ast.parse(text, filename=rel)
    except SyntaxError:
        return FileEntities(path=rel)
    lines = text.splitlines()
    fe = FileEntities(path=rel)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                fe.imports.append(
                    CodeEntity(
                        kind="import",
                        name=alias.name,
                        file=rel,
                        lineno=node.lineno,
                        end_lineno=getattr(node, "end_lineno", node.lineno) ,
                        source=alias.name,
                    )
                )
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for alias in node.names:
                full = f"{mod}.{alias.name}" if mod else alias.name
                fe.imports.append(
                    CodeEntity(
                        kind="import",
                        name=full,
                        file=rel,
                        lineno=node.lineno,
                        end_lineno=getattr(node, "end_lineno", node.lineno),
                        source=full,
                    )
                )
        elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
            # only top-level + method defs; ast.walk will catch both, dedup by lineno
            start = node.lineno
            end = getattr(node, "end_lineno", start) or start
            src = "\n".join(lines[start - 1 : end]) if lines else ""
            fe.functions.append(
                CodeEntity(
                    kind="function",
                    name=node.name,
                    file=rel,
                    lineno=start,
                    end_lineno=end,
                    docstring=ast.get_docstring(node),
                    source=src,
                )
            )
        elif isinstance(node, ast.ClassDef):
            start = node.lineno
            end = getattr(node, "end_lineno", start) or start
            src = "\n".join(lines[start - 1 : end]) if lines else ""
            fe.classes.append(
                CodeEntity(
                    kind="class",
                    name=node.name,
                    file=rel,
                    lineno=start,
                    end_lineno=end,
                    docstring=ast.get_docstring(node),
                    source=src,
                )
            )
    # dedup by (kind,name,lineno)
    seen = set()
    for lst in (fe.imports, fe.functions, fe.classes):
        uniq = []
        for e in lst:
            key = (e.kind, e.name, e.lineno)
            if key not in seen:
                seen.add(key)
                uniq.append(e)
        lst[:] = uniq
    return fe


def parse_repo(repo_root: Path) -> dict[str, FileEntities]:
    result: dict[str, FileEntities] = {}
    for p in repo_root.rglob("*.py"):
        if ".git" in p.parts or "__pycache__" in p.parts:
            continue
        fe = parse_file(repo_root, p)
        result[fe.path] = fe
    return result
