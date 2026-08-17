"""Dense embedding model, wrapped once as a module-level singleton.

fastembed's `passage_embed` / `query_embed` apply the model-specific
asymmetric prefix (BGE models expect a different instruction prefix for a
query than for the passages it's matched against) so callers never have to
think about that themselves.
"""

from functools import lru_cache

from fastembed import TextEmbedding

from app.config import EMBEDDING_MODEL


@lru_cache(maxsize=1)
def _model() -> TextEmbedding:
    return TextEmbedding(model_name=EMBEDDING_MODEL)


def embed_passages(texts: list[str]) -> list[list[float]]:
    return [vec.tolist() for vec in _model().passage_embed(texts)]


def embed_query(text: str) -> list[float]:
    return next(iter(_model().query_embed([text]))).tolist()
