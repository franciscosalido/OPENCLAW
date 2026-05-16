"""Pure retrieval evaluation metrics for OpenClaw.

The public API intentionally matches the Sprint RAG-1A PR-02 implementation
contract. ``mean_average_precision`` is not exported in this PR because the
final contract lists precision, recall, reciprocal-rank, NDCG and latency
metrics only; MAP needs a separate mathematical convention for AP@k before it
can be added safely.
"""

from __future__ import annotations

from evaluation.eval_latency import latency_percentiles
from evaluation.eval_mrr import mean_reciprocal_rank, reciprocal_rank
from evaluation.eval_ndcg import dcg_at_k, mean_ndcg_at_k, ndcg_at_k
from evaluation.eval_precision import mean_precision_at_k, precision_at_k
from evaluation.eval_recall import mean_recall_at_k, recall_at_k

__all__ = [
    "dcg_at_k",
    "latency_percentiles",
    "mean_precision_at_k",
    "mean_recall_at_k",
    "mean_ndcg_at_k",
    "mean_reciprocal_rank",
    "ndcg_at_k",
    "precision_at_k",
    "recall_at_k",
    "reciprocal_rank",
]
