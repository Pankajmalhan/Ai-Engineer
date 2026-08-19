"""Loads and caches the three shortlisted embedding models, and embeds
chunks/queries with each model's own asymmetric query/passage convention
(get this wrong and you silently lose retrieval quality -- see
concept.md's "Common pitfalls").

late_chunking is the one strategy that never calls embed_passages() here:
Chonkie's LateChunker already produced a mean-pooled embedding per chunk as
part of chunking (see chunkers.py's Chunk.embedding), so run_grid.py uses
that directly instead of re-embedding the chunk text in isolation -- doing
otherwise would defeat the entire point of late chunking (the chunk would
lose the whole-document context it was built to preserve).
"""

from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from sentence_transformers import SentenceTransformer

MODELS = [
    "BAAI/bge-small-en-v1.5",
    "nomic-ai/modernbert-embed-base",
    "Snowflake/snowflake-arctic-embed-m",
]


@dataclass(frozen=True)
class ModelSpec:
    name: str
    query_prefix: str
    passage_prefix: str


MODEL_SPECS = {
    "BAAI/bge-small-en-v1.5": ModelSpec(
        name="BAAI/bge-small-en-v1.5",
        query_prefix="Represent this sentence for searching relevant passages: ",
        passage_prefix="",
    ),
    "nomic-ai/modernbert-embed-base": ModelSpec(
        name="nomic-ai/modernbert-embed-base",
        query_prefix="search_query: ",
        passage_prefix="search_document: ",
    ),
    "Snowflake/snowflake-arctic-embed-m": ModelSpec(
        name="Snowflake/snowflake-arctic-embed-m",
        query_prefix="Represent this sentence for searching relevant passages: ",
        passage_prefix="",
    ),
}


@lru_cache(maxsize=len(MODELS))
def _model(model_name: str) -> SentenceTransformer:
    # device="cpu": ModernBERT's attention path deadlocks on Apple's MPS
    # backend (forward pass hangs forever, Metal command queue idle, main
    # thread parked on a mutex) -- not a download/auth issue. CPU is slower
    # but actually completes; see the matching note in chunkers.py.
    return SentenceTransformer(model_name, device="cpu")


def embed_passages(texts: list[str], model_name: str) -> np.ndarray:
    spec = MODEL_SPECS[model_name]
    prefixed = [spec.passage_prefix + t for t in texts]
    return _model(model_name).encode(
        prefixed, batch_size=32, show_progress_bar=True, normalize_embeddings=True
    )


def embed_queries(texts: list[str], model_name: str) -> np.ndarray:
    spec = MODEL_SPECS[model_name]
    prefixed = [spec.query_prefix + t for t in texts]
    return _model(model_name).encode(
        prefixed, batch_size=32, show_progress_bar=False, normalize_embeddings=True
    )
