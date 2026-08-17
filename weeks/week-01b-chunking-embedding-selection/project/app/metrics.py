"""recall@k and NDCG@k, evaluated at chunk granularity but scored back at
document granularity: a query has exactly one relevant *document* (see
corpus.py), but that document is split into N chunks by whatever chunking
strategy produced the index, and any of those N chunks showing up in the
results counts as the document being found.

This matters for NDCG's ideal ranking (IDCG): the "perfect" result set for a
query isn't one relevant chunk followed by nine irrelevant ones -- it's
*all* of the relevant document's chunks (up to k), since every one of them
is a correct, on-topic result. Capping the ideal count at
min(relevant_chunk_count, k) is what makes NDCG@k comparable across chunking
strategies that split the same document into very different numbers of
chunks (e.g. semantic's ~300 tiny chunks vs. fixed-size's ~20).
"""

import math


def recall_at_k(retrieved_doc_ids: list[str], relevant_doc_id: str, k: int = 10) -> int:
    return int(relevant_doc_id in retrieved_doc_ids[:k])


def ndcg_at_k(
    retrieved_doc_ids: list[str],
    relevant_doc_id: str,
    relevant_chunk_count: int,
    k: int = 10,
) -> float:
    """retrieved_doc_ids: doc_id of each of the top-k retrieved *chunks*,
    ranked best-first. relevant_chunk_count: how many chunks in the index
    belong to relevant_doc_id (needed to compute the ideal ranking)."""
    dcg = sum(
        1.0 / math.log2(rank + 1)
        for rank, doc_id in enumerate(retrieved_doc_ids[:k], start=1)
        if doc_id == relevant_doc_id
    )
    ideal_hits = min(relevant_chunk_count, k)
    idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
    return dcg / idcg if idcg > 0 else 0.0
