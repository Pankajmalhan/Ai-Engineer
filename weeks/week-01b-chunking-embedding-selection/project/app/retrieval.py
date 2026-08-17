"""Builds a chunk-embedding index for one (model, strategy) combination and
searches it. Embeddings are L2-normalized (see embeddings.py), so cosine
similarity is a plain dot product -- the whole index search is one matrix
multiply, vectorized across every query at once.
"""

from dataclasses import dataclass

import numpy as np

from app.chunkers import Chunk, chunk_corpus
from app.embeddings import embed_passages, embed_queries


@dataclass
class ChunkIndex:
    chunks: list[Chunk]
    vectors: np.ndarray  # (n_chunks, dim), L2-normalized

    def relevant_chunk_count(self, doc_id: str) -> int:
        return sum(1 for c in self.chunks if c.doc_id == doc_id)


def build_index(docs: list[dict], strategy: str, model_name: str) -> ChunkIndex:
    chunks = chunk_corpus(docs, strategy, model_name)

    # late_chunking chunks already carry an embedding from Chonkie (mean-pooled
    # from the whole document's token embeddings) -- everything else needs a
    # normal passage-embedding pass over the chunk text.
    if strategy == "late_chunking":
        vectors = np.array([c.embedding for c in chunks], dtype=np.float32)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        vectors = vectors / norms
    else:
        vectors = embed_passages([c.text for c in chunks], model_name).astype(np.float32)

    return ChunkIndex(chunks=chunks, vectors=vectors)


def search(index: ChunkIndex, queries: list[str], model_name: str, k: int = 10) -> list[list[str]]:
    """Returns, per query, the doc_id of each of the top-k retrieved chunks
    (ranked best-first)."""
    query_vecs = embed_queries(queries, model_name).astype(np.float32)
    sims = query_vecs @ index.vectors.T  # (n_queries, n_chunks)
    top_k_idx = np.argsort(-sims, axis=1)[:, :k]
    return [[index.chunks[i].doc_id for i in row] for row in top_k_idx]
