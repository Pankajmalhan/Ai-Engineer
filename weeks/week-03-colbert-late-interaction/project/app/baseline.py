"""Single-vector bi-encoder baseline, over the *same* passages the ColBERT
index in app/index.py sees -- reuses RAGatouille's own sentence splitter so
neither side gets an advantage from different chunk boundaries. This is
what app/compare.py measures ColBERT's per-token MaxSim scoring against.
"""

import json
from functools import lru_cache
from pathlib import Path

import numpy as np
from ragatouille.data.preprocessors import llama_index_sentence_splitter
from sentence_transformers import SentenceTransformer

from app.config import BIENCODER_MODEL
from app.corpus import load_corpus

DATA_DIR = Path(__file__).parent.parent / "data"
EMBEDDINGS_PATH = DATA_DIR / "baseline_embeddings.npy"
PASSAGES_PATH = DATA_DIR / "baseline_passages.json"

# BGE models need an instruction prefix on the *query* side only -- the
# passage side is embedded as-is. Same convention Week 1/2 use via
# fastembed's query_embed/passage_embed; spelled out explicitly here since
# this project calls sentence-transformers directly instead.
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


@lru_cache(maxsize=1)
def _model() -> SentenceTransformer:
    return SentenceTransformer(BIENCODER_MODEL)


def build_baseline() -> None:
    titles, texts, ids = load_corpus()
    chunks = llama_index_sentence_splitter(texts, ids, chunk_size=256)
    passages = [c["content"] for c in chunks]
    doc_ids = [c["document_id"] for c in chunks]

    print(f"Embedding {len(passages)} passages with {BIENCODER_MODEL}...")
    model = _model()
    embeddings = model.encode(passages, normalize_embeddings=True, show_progress_bar=True)

    DATA_DIR.mkdir(exist_ok=True)
    np.save(EMBEDDINGS_PATH, embeddings.astype(np.float32))
    PASSAGES_PATH.write_text(
        json.dumps(
            [{"document_id": d, "content": p} for d, p in zip(doc_ids, passages)],
            indent=2,
        )
    )
    print(f"Saved {len(passages)} embeddings ({embeddings.shape[1]}-dim) to {EMBEDDINGS_PATH}")


def load_baseline() -> tuple[np.ndarray, list[dict]]:
    if not EMBEDDINGS_PATH.exists():
        raise FileNotFoundError(
            "No baseline embeddings found -- run `uv run python -m app.baseline` first."
        )
    embeddings = np.load(EMBEDDINGS_PATH)
    passages = json.loads(PASSAGES_PATH.read_text())
    return embeddings, passages


def search_baseline(query: str, k: int, embeddings: np.ndarray, passages: list[dict]) -> list[dict]:
    query_vec = _model().encode([QUERY_PREFIX + query], normalize_embeddings=True)[0]
    # embeddings are pre-normalized, so a plain dot product is cosine similarity.
    scores = embeddings @ query_vec
    top_idx = np.argsort(-scores)[:k]
    return [
        {
            "rank": rank + 1,
            "score": float(scores[i]),
            "document_id": passages[i]["document_id"],
            "content": passages[i]["content"],
        }
        for rank, i in enumerate(top_idx)
    ]


if __name__ == "__main__":
    build_baseline()
