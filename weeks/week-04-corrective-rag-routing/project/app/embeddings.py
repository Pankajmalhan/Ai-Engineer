"""Real dense embeddings for the pgvector leg of hybrid_search.

Same model family as Week 1's bi-encoder (BAAI/bge-small-en-v1.5), loaded once and
reused -- this replaces the earlier version of this project's TF-IDF-as-a-dense-proxy
stand-in now that there's a real vector store to put real embeddings in.
"""

from __future__ import annotations

import os
from functools import lru_cache

EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
EMBEDDING_DIM = 384  # bge-small-en-v1.5's output dimension; must match the pgvector column


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(EMBEDDING_MODEL)


def embed(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    vectors = _model().encode(list(texts), normalize_embeddings=True)
    return vectors.tolist()


def embed_one(text: str) -> list[float]:
    return embed([text])[0]
