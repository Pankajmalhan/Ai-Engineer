"""Stage 1 of the two-stage pipeline: broad recall via the Week 1 hybrid
(dense + sparse, RRF-fused) retriever -- unchanged from Week 1 except that
the fused output is truncated to RERANK_POOL_SIZE candidates instead of a
final top_k, since Stage 2 (rerankers.py) still has to narrow that pool
down further. See concept.md for why the pool has to stay wider than the
final result list for reranking to have anything to do.
"""

import psycopg
from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode

from app import db
from app.config import CANDIDATE_POOL_SIZE, RERANK_POOL_SIZE
from app.embeddings import embed_query
from app.fusion import DEFAULT_K, rrf_fuse


def _row_to_node(row: tuple[int, str, str, float], score: float) -> NodeWithScore:
    doc_id, title, content, _raw = row
    node = TextNode(id_=str(doc_id), text=content, metadata={"title": title})
    return NodeWithScore(node=node, score=score)


class HybridRRFRetriever(BaseRetriever):
    """Runs dense + sparse retrieval over the same corpus and fuses the two
    ranked candidate lists with Reciprocal Rank Fusion -- Week 1's retriever,
    reused as-is for Stage 1 candidate generation."""

    def __init__(
        self,
        conn: psycopg.Connection,
        top_k: int = RERANK_POOL_SIZE,
        candidate_pool_size: int = CANDIDATE_POOL_SIZE,
        rrf_k: int = DEFAULT_K,
    ):
        self._conn = conn
        self._top_k = top_k
        self._candidate_pool_size = candidate_pool_size
        self._rrf_k = rrf_k
        super().__init__()

    def _retrieve(self, query_bundle: QueryBundle) -> list[NodeWithScore]:
        query_vec = embed_query(query_bundle.query_str)
        dense_rows = db.dense_search(self._conn, query_vec, self._candidate_pool_size)
        sparse_rows = db.sparse_search(
            self._conn, query_bundle.query_str, self._candidate_pool_size
        )

        rows_by_id = {row[0]: row for row in dense_rows}
        rows_by_id.update({row[0]: row for row in sparse_rows})

        dense_ranked_ids = [row[0] for row in dense_rows]
        sparse_ranked_ids = [row[0] for row in sparse_rows]
        fused = rrf_fuse(
            [dense_ranked_ids, sparse_ranked_ids], k=self._rrf_k, top_k=self._top_k
        )

        return [_row_to_node(rows_by_id[doc_id], score) for doc_id, score in fused]


def hybrid_candidates(
    conn: psycopg.Connection, query: str, pool_size: int = RERANK_POOL_SIZE
) -> list[tuple[int, str, str]]:
    """Convenience wrapper for benchmark.py / rerankers.py: returns Stage 1's
    fused candidates as plain (doc_id, title, content) tuples, hybrid-ranked
    best-first, ready to hand to a reranker's rerank(query, candidates, ...).
    """
    retriever = HybridRRFRetriever(conn, top_k=pool_size)
    nodes = retriever.retrieve(QueryBundle(query_str=query))
    return [
        (int(n.node.id_), n.node.metadata["title"], n.node.text) for n in nodes
    ]
