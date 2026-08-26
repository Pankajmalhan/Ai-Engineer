"""hybrid_search: BM25 (sparse, in-memory) + pgvector (dense, real embeddings),
combined by reciprocal rank fusion (RRF) -- the actual Week 1 hybrid-search technique,
now backed by a real vector store instead of a TF-IDF stand-in.

Both the FACTUAL and CODE routes call this same function against different pgvector
`collection`s (see app/pipeline.py) with different `bm25_weight`/`dense_weight`: code
queries usually hinge on an exact identifier or error string matching lexically, so the
CODE route weights BM25 more heavily rather than reaching for a separate retrieval
algorithm (e.g. ColBERT/PLAID) -- see concept.md's "Query routing" section for why that
tradeoff (a cheaper Postgres-only stack vs. ColBERT's token-level precision) makes
sense for a query router with only two retrieval-needing branches.
"""

from __future__ import annotations

from rank_bm25 import BM25Okapi

from app.config import TOP_K
from app.models import RetrievedChunk
from app.vectorstore import PGVectorStore

RRF_K = 60


def _tokenize(text: str) -> list[str]:
    return text.lower().split()


def hybrid_search(
    query: str,
    store: PGVectorStore,
    collection: str,
    top_k: int = TOP_K,
    candidate_k: int = 20,
    bm25_weight: float = 1.0,
    dense_weight: float = 1.0,
) -> list[RetrievedChunk]:
    docs = store.all_documents(collection)
    if not docs:
        return []
    docs_by_id = {doc.id: doc for doc in docs}

    bm25 = BM25Okapi([_tokenize(doc.text) for doc in docs])
    bm25_scores = bm25.get_scores(_tokenize(query))
    bm25_ranked_ids = [
        docs[i].id
        for i in sorted(range(len(docs)), key=lambda i: bm25_scores[i], reverse=True)[:candidate_k]
    ]

    dense_ranked_ids = [c.id for c in store.similarity_search(collection, query, top_k=candidate_k)]

    fused: dict[str, float] = {}
    for rank, doc_id in enumerate(bm25_ranked_ids):
        fused[doc_id] = fused.get(doc_id, 0.0) + bm25_weight / (RRF_K + rank + 1)
    for rank, doc_id in enumerate(dense_ranked_ids):
        fused[doc_id] = fused.get(doc_id, 0.0) + dense_weight / (RRF_K + rank + 1)

    ranked_ids = sorted(fused, key=lambda doc_id: fused[doc_id], reverse=True)[:top_k]
    return [
        RetrievedChunk(id=doc_id, text=docs_by_id[doc_id].text, score=fused[doc_id])
        for doc_id in ranked_ids
    ]
