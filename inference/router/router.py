from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from inference.models.base import LLMProvider


class ModelTier(str, Enum):
    CHEAP = "cheap"    # Tier 1: Fast & lightweight, low-cost (e.g. gpt-oss-20b, llama-3.1-8b)
    HEAVY = "heavy"    # Tier 2: Flagship deep reasoning (e.g. gpt-oss-120b, gpt-4o)


@dataclass
class RoutingDecision:
    tier: ModelTier
    model_name: str
    reason: str
    complexity_score: float  # 0.0 to 1.0
    escalated: bool = False


# Keyword signal banks
HARD_KEYWORDS = {
    "deadlock", "concurrency", "asyncio", "thread", "threading", "recursion",
    "recursive", "algorithm", "tree", "graph", "memory", "leak", "race condition",
    "architecture", "refactor", "performance", "optimization", "complex",
}

EASY_KEYWORDS = {
    "typo", "syntax", "add", "addition", "subtract", "subtraction", "multiply",
    "sign", "negative", "negatives", "returns 0", "returns none", "not implemented",
    "docstring", "comment", "off-by-one", "off by one", "rename", "reverse",
}


class ModelRouter:
    """Dynamic task complexity classifier and tiered model router with cascade escalation."""

    def __init__(
        self,
        cheap_model: str = "openai/gpt-oss-20b",
        heavy_model: str = "openai/gpt-oss-120b",
        use_mock: bool = False,
        complexity_threshold: float = 0.50,
    ):
        self.use_mock = use_mock
        if use_mock:
            self.cheap_model = "mock-gpt-4o-mini-cheap"
            self.heavy_model = "mock-gpt-4o-mini"
        else:
            self.cheap_model = cheap_model
            self.heavy_model = heavy_model
        self.threshold = complexity_threshold

    def calculate_complexity(
        self,
        issue: str,
        context: str = "",
        candidate_files: Optional[list[str]] = None,
    ) -> tuple[float, list[str]]:
        """Compute a continuous complexity score between 0.0 (trivial) and 1.0 (very complex)."""
        score = 0.25  # baseline
        reasons = []

        issue_lower = issue.lower()

        # 1. Hard keyword signals (+0.35)
        matched_hard = [w for w in HARD_KEYWORDS if re.search(rf"\b{re.escape(w)}\b", issue_lower)]
        if matched_hard:
            score += 0.35
            reasons.append(f"hard keywords: {matched_hard[:2]}")

        # 2. Easy keyword signals (-0.15)
        matched_easy = [w for w in EASY_KEYWORDS if re.search(rf"\b{re.escape(w)}\b", issue_lower)]
        if matched_easy and not matched_hard:
            score -= 0.15
            reasons.append(f"easy keywords: {matched_easy[:2]}")

        # 3. Context size signals
        ctx_len = len(context)
        if ctx_len > 4000:
            score += 0.25
            reasons.append("large context (>4k chars)")
        elif ctx_len > 2000:
            score += 0.15
            reasons.append("moderate context (>2k chars)")
        elif ctx_len > 0 and ctx_len < 800:
            score -= 0.10
            reasons.append("compact context (<800 chars)")

        # 4. Multi-file scope signals
        files = candidate_files or []
        if len(files) > 2:
            score += 0.20
            reasons.append(f"multi-file scope ({len(files)} files)")
        elif len(files) == 1:
            score -= 0.05
            reasons.append("single file scope")

        # Clamp between 0.0 and 1.0
        final_score = round(max(0.0, min(1.0, score)), 2)
        return final_score, reasons

    def route(
        self,
        issue: str,
        context: str = "",
        candidate_files: Optional[list[str]] = None,
    ) -> RoutingDecision:
        """Classify task and assign initial model tier."""
        score, reasons = self.calculate_complexity(issue, context, candidate_files)

        if score < self.threshold:
            tier = ModelTier.CHEAP
            model_name = self.cheap_model
            reason_desc = f"Tier 1 [Cheap]: score {score:.2f} < {self.threshold:.2f} ({', '.join(reasons)})"
        else:
            tier = ModelTier.HEAVY
            model_name = self.heavy_model
            reason_desc = f"Tier 2 [Heavy]: score {score:.2f} >= {self.threshold:.2f} ({', '.join(reasons)})"

        return RoutingDecision(
            tier=tier,
            model_name=model_name,
            reason=reason_desc,
            complexity_score=score,
            escalated=False,
        )

    def escalate(
        self,
        current_decision: RoutingDecision,
        failure_reason: str = "",
    ) -> RoutingDecision:
        """Escalate from Tier 1 (cheap) to Tier 2 (heavy) if tests fail during execution."""
        if current_decision.tier == ModelTier.CHEAP:
            reason = f"Escalated to Tier 2 [Heavy] ({self.heavy_model}) following test failure: {failure_reason[:80]}"
            return RoutingDecision(
                tier=ModelTier.HEAVY,
                model_name=self.heavy_model,
                reason=reason,
                complexity_score=max(0.80, current_decision.complexity_score),
                escalated=True,
            )
        return current_decision
