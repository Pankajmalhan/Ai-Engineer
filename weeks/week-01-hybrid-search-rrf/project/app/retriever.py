"""Retrievers built on LlamaIndex's BaseRetriever interface, backed by the
raw pgvector / pg_search SQL in db.py.

LlamaIndex doesn't ship a built-in ParadeDB BM25 integration, so the dense
and sparse candidate generation happen in plain SQL (db.py) and get wrapped
here as LlamaIndex NodeWithScore results — the shape any LlamaIndex-based
RAG pipeline downstream expects from a retriever, regardless of what's
generating candidates underneath.
"""

import psycopg
from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode

from app import db
from app.embeddings import embed_query
from app.fusion import DEFAULT_K, rrf_fuse

CANDIDATE_POOL_SIZE = 50


def _row_to_node(row: tuple[int, str, str, float], score: float) -> NodeWithScore:
    doc_id, title, content, _raw = row
    node = TextNode(id_=str(doc_id), text=content, metadata={"title": title})
    return NodeWithScore(node=node, score=score)


class DenseRetriever(BaseRetriever):
    def __init__(self, conn: psycopg.Connection, top_k: int = 10):
        self._conn = conn
        self._top_k = top_k
        super().__init__()

    def _retrieve(self, query_bundle: QueryBundle) -> list[NodeWithScore]:
        query_vec = embed_query(query_bundle.query_str)
        rows = db.dense_search(self._conn, query_vec, self._top_k)
        # cosine distance: smaller is better -> convert to a similarity score
        return [_row_to_node(row, 1.0 - row[3]) for row in rows]


class SparseRetriever(BaseRetriever):
    def __init__(self, conn: psycopg.Connection, top_k: int = 10):
        self._conn = conn
        self._top_k = top_k
        super().__init__()

    def _retrieve(self, query_bundle: QueryBundle) -> list[NodeWithScore]:
        rows = db.sparse_search(self._conn, query_bundle.query_str, self._top_k)
        return [_row_to_node(row, row[3]) for row in rows]


class HybridRRFRetriever(BaseRetriever):
    """Runs dense + sparse retrieval over the same corpus and fuses the two
    ranked candidate lists with Reciprocal Rank Fusion."""

    def __init__(
        self,
        conn: psycopg.Connection,
        top_k: int = 10,
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
