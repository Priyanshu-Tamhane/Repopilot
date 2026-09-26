"""Compare two benchmark runs (e.g. Exp1 vs Exp2) per Spec s6.

Usage:
  python -m evaluation.experiments.compare evaluation/results/exp1_*.json evaluation/results/exp2_*.json
Outputs a delta table + retrieval accuracy (hit@k) if retrieval traces exist.
"""
from __future__ import annotations

import argparse
import json
import glob
from pathlib import Path
from typing import Optional


def load_latest(pattern: str) -> Path:
    matches = sorted(glob.glob(pattern))
    if not matches:
        raise FileNotFoundError(f"no match for {pattern}")
    return Path(matches[-1])


def load_metrics(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def pct_delta(new: float, old: float) -> str:
    if old == 0:
        return "n/a"
    d = (new - old) / old * 100
    sign = "+" if d > 0 else ""
    return f"{sign}{d:.1f}%"


def main() -> None:
    ap = argparse.ArgumentParser(description="Compare two benchmark JSONs (Spec s6: tokens/latency/success/retrieval)")
    ap.add_argument("baseline", help="baseline JSON (exp1)")
    ap.add_argument("candidate", help="candidate JSON (exp2)")
    args = ap.parse_args()

    bl = load_metrics(Path(args.baseline))
    ca = load_metrics(Path(args.candidate))

    bm = bl["metrics"]
    cm = ca["metrics"]

    print(f"Baseline : {bl['experiment']} {bl['dataset']} -> {args.baseline}")
    print(f"Candidate: {ca['experiment']} {ca['dataset']} -> {args.candidate}")
    print()
    print("| Metric | Baseline | Candidate | Delta |")
    print("|---|---|---|---|")
    def row(name, b, c, fmt=".2f", suffix=""):
        delta = pct_delta(c, b) if isinstance(b, (int, float)) and isinstance(c, (int, float)) else "n/a"
        bf = f"{b:{fmt}}{suffix}" if isinstance(b, (int, float)) else str(b)
        cf = f"{c:{fmt}}{suffix}" if isinstance(c, (int, float)) else str(c)
        print(f"| {name} | {bf} | {cf} | {delta} |")

    row("Success rate", bm["success_rate"]*100, cm["success_rate"]*100, ".1f", "%")
    row("Test pass rate", bm["test_pass_rate"]*100, cm["test_pass_rate"]*100, ".1f", "%")
    row("Patch rate", bm["patch_rate"]*100, cm["patch_rate"]*100, ".1f", "%")
    row("Avg latency (s)", bm["avg_latency"], cm["avg_latency"], ".2f")
    row("Median latency (s)", bm["median_latency"], cm["median_latency"], ".2f")
    row("P95 latency (s)", bm["p95_latency"], cm["p95_latency"], ".2f")
    row("Total tokens", bm["total_tokens"], cm["total_tokens"], ".0f")
    row("Avg tokens/task", bm["avg_tokens_per_task"], cm["avg_tokens_per_task"], ".0f")
    row("LLM calls total", bm["total_llm_calls"], cm["total_llm_calls"], ".0f")
    row("Cost/task ($)", bm["cost_per_task"], cm["cost_per_task"], ".4f")
    row("Avg tool calls/task", bm["avg_tool_calls_per_task"], cm["avg_tool_calls_per_task"], ".1f")
    row("Tasks/min", bm.get("tasks_per_minute") or 0, cm.get("tasks_per_minute") or 0, ".1f")

    # Tokens saved if candidate had retrieval traces saving full vs context
    # We compute from metrics avg tokens: tokens_saved% = (baseline - candidate)/baseline
    tokens_saved = pct_delta(cm["total_tokens"], bm["total_tokens"])
    print()
    if tokens_saved.startswith("-"):
        print(f"Tokens saved: {tokens_saved} (candidate used fewer tokens)")
    else:
        print(f"Tokens delta: {tokens_saved}")

    # Success delta gate per spec
    succ_delta = cm["success_rate"] - bm["success_rate"]
    print(f"Success delta: {succ_delta:+.1%}" + ("  PASS (no regression)" if succ_delta >= 0 else "  FAIL (candidate regressed)"))


if __name__ == "__main__":
    main()
