from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass

_TOKEN_RE = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*|[0-9]+")


def tokenize(text: str) -> list[str]:
    toks = _TOKEN_RE.findall(text.lower())
    # split snake_case and camelCase-ish: keep original + parts
    out: list[str] = []
    for t in toks:
        out.append(t)
        if "_" in t:
            out.extend(p for p in t.split("_") if p)
    return out


@dataclass
class TfIdfModel:
    vocab: dict[str, int]
    idf: dict[str, float]
    doc_vectors: list[dict[str, float]]  # sparse, l2-normalized
    doc_norms: list[float]


def build_tfidf(docs: list[str]) -> TfIdfModel:
    n = len(docs)
    if n == 0:
        return TfIdfModel({}, {}, [], [])
    tokenized = [tokenize(d) for d in docs]
    df: Counter[str] = Counter()
    for toks in tokenized:
        for t in set(toks):
            df[t] += 1
    vocab = {t: i for i, t in enumerate(sorted(df.keys()))}
    idf = {t: math.log((n + 1) / (c + 1)) + 1 for t, c in df.items()}

    doc_vectors: list[dict[str, float]] = []
    doc_norms: list[float] = []
    for toks in tokenized:
        tf = Counter(toks)
        total = len(toks) or 1
        vec: dict[str, float] = {}
        for t, c in tf.items():
            vec[t] = (c / total) * idf[t]
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        # l2 normalize
        for t in list(vec.keys()):
            vec[t] /= norm
        doc_vectors.append(vec)
        doc_norms.append(norm)
    return TfIdfModel(vocab=vocab, idf=idf, doc_vectors=doc_vectors, doc_norms=doc_norms)


def embed_query(query: str, model: TfIdfModel) -> dict[str, float]:
    toks = tokenize(query)
    if not toks:
        return {}
    tf = Counter(toks)
    total = len(toks)
    vec: dict[str, float] = {}
    for t, c in tf.items():
        if t in model.idf:
            vec[t] = (c / total) * model.idf[t]
    norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
    for t in list(vec.keys()):
        vec[t] /= norm
    return vec


def cosine_sparse(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    # iterate smaller
    if len(a) > len(b):
        a, b = b, a
    s = 0.0
    for k, v in a.items():
        if k in b:
            s += v * b[k]
    return s  # already l2-normalized
