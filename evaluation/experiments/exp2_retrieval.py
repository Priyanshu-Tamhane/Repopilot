"""Experiment 2 — Retrieval (Spec s15).

Same single agent + same model as Exp1, but with repository-aware RAG:
issue -> TF-IDF retrieval -> relevant files/functions -> dependency expansion -> relevant tests -> LLM context.
Compare vs Exp1 on tokens saved, latency, success rate, retrieval accuracy.
"""
EXPERIMENT = {
    "name": "exp2_retrieval",
    "description": "Single agent + repository RAG (TF-IDF, top-k=6, 8k char budget)",
    "agent": "baseline+retrieval",
    "dataset": "repopilot-seed v1.0",
    "config": {
        "retrieval": True,
        "multi_agent": False,
        "model_routing": False,
        "caching": False,
        "parallel": False,
        "retrieval_top_k": 6,
        "retrieval_budget_chars": 8000,
        "embeddings": "tfidf",
    },
}
