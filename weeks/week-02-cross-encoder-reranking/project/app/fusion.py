"""Reciprocal Rank Fusion — pure, DB-free, so it's independently unit-testable.

RRF(d) = sum over each ranked list containing d of  1 / (k + rank_in_that_list)

A document missing from a list contributes 0 for that list, not a penalty
based on an assumed rank past the end of the list.
"""

DEFAULT_K = 60


def rrf_fuse(
    ranked_lists: list[list[int]], k: int = DEFAULT_K, top_k: int | None = None
) -> list[tuple[int, float]]:
    scores: dict[int, float] = {}
    for ranked_list in ranked_lists:
        for rank, doc_id in enumerate(ranked_list, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)

    fused = sorted(scores.items(), key=lambda pair: pair[1], reverse=True)
    return fused[:top_k] if top_k is not None else fused
