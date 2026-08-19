"""NDCG@10 -- pure, DB-free, so it's independently unit-testable (see
test_metrics.py) against the worked example in concept.md.

DCG@k  = sum_{i=1}^{k} rel_i / log2(i + 1)      (i is the 1-indexed rank)
IDCG@k = DCG@k of the ideal ordering (all relevant docs ranked first)
NDCG@k = DCG@k / IDCG@k                          (0 if IDCG is 0)

Every query in this benchmark's corpus.py has exactly one relevant document
(binary relevance), which collapses IDCG@10 to a constant: 1 / log2(2) = 1
whenever the relevant doc could in principle appear in the top 10 at all.
So for this benchmark specifically, NDCG@10 reduces to 1/log2(rank+1) for
the rank the relevant doc actually lands at (0 if it's outside the top 10)
-- but the implementation below doesn't hard-code that; it's the general
multi-relevant-document formula, so it stays correct if the query set ever
grows graded or multi-document relevance judgments.
"""

import math


def ndcg_at_k(ranked_ids: list[int], relevant_ids: set[int], k: int = 10) -> float:
    """NDCG@k for one query: how close ranked_ids' ordering got to the best
    possible ordering, weighted so hits near the top count more than hits
    near the bottom.

    Args:
        ranked_ids: doc ids in ranked order, best-first (e.g. a reranker's
            or the hybrid retriever's output for one query).
        relevant_ids: the ground-truth relevant doc ids for that query
            (usually just one, in this project's benchmark corpus).
        k: cutoff -- only the first k entries of ranked_ids are scored.

    Returns:
        A float in [0.0, 1.0]. 1.0 means every relevant doc is packed at
        the very front (rank 1, 2, 3, ...) -- the best ordering possible.
        0.0 means none of the relevant docs made it into the top k at all.
    """
    top_k = ranked_ids[:k]

    # DCG: walk the actual top-k ranking (rank = 1-indexed position) and add
    # 1/log2(rank+1) for every position that's a true relevant doc. A hit at
    # rank 1 contributes 1.0; the same hit at rank 9 contributes only ~0.29
    # -- that log2 discount is what makes this "rank-aware" instead of the
    # binary hit-or-miss that recall_at_k below gives you.
    dcg = sum(
        1.0 / math.log2(rank + 1)
        for rank, doc_id in enumerate(top_k, start=1)
        if doc_id in relevant_ids
    )

    # IDCG: the same discounted sum, but for the *best possible* ordering --
    # every relevant doc pushed to the front (rank 1, 2, 3, ...), capped at
    # k since anything past the cutoff can't be scored anyway. This is the
    # ceiling DCG could ever reach for this query's relevant set.
    ideal_hits = min(len(relevant_ids), k)
    idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))

    # Normalize actual DCG against that ceiling so the result is always a
    # 0-1 score, comparable across queries with different relevant-doc
    # counts. idcg is 0 only when relevant_ids is empty (no ceiling to
    # measure against), so that's the one case we return 0.0 outright.
    return dcg / idcg if idcg > 0 else 0.0


def recall_at_k(ranked_ids: list[int], relevant_ids: set[int], k: int = 10) -> int:
    """Binary hit/miss, kept alongside NDCG for continuity with Week 1's
    benchmark table -- see concept.md's "Why NDCG and not just recall" for
    why recall@10 alone can't show reranking's effect once Week 1 already
    saturates it."""
    return int(bool(relevant_ids & set[int](ranked_ids[:k])))
