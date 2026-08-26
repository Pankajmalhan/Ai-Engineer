"""Build the ColBERT/PLAID index (Stage 1 of this week's project) from the
Wikipedia corpus in app/corpus.py, via RAGatouille.

RAGatouille's `.index()` does three things in one call: splits each article
into <=256-token passages (`split_documents=True`, the default), runs every
passage through the ColBERT checkpoint to get one 128-dim embedding per
token, then builds a PLAID index over all of those token embeddings
(residual-compressed centroid clustering -- see concept.md). The document
count you pass in and the *passage* count that ends up indexed are
different numbers on purpose -- see the printed summary this script ends
with, and README.md for what was actually measured on this corpus.
"""

import json
import time
from pathlib import Path

from ragatouille import RAGPretrainedModel

from app.config import COLBERT_CHECKPOINT, INDEX_NAME
from app.corpus import load_corpus

DATA_DIR = Path(__file__).parent.parent / "data"


def build_index() -> str:
    titles, texts, ids = load_corpus()
    print(f"Loaded {len(titles)} articles ({sum(len(t) for t in texts):,} characters total).")

    RAG = RAGPretrainedModel.from_pretrained(COLBERT_CHECKPOINT)

    start = time.perf_counter()
    index_path = RAG.index(
        index_name=INDEX_NAME,
        collection=texts,
        document_ids=ids,
        document_metadatas=[{"title": t} for t in titles],
        max_document_length=256,
        split_documents=True,
    )
    elapsed_s = time.perf_counter() - start

    passage_count = _count_indexed_passages(index_path)
    print(f"\nIndexed {len(titles)} articles -> {passage_count} passages in {elapsed_s:.1f}s.")
    print(f"Index written to: {index_path}")

    DATA_DIR.mkdir(exist_ok=True)
    (DATA_DIR / "index_stats.json").write_text(
        json.dumps(
            {
                "article_count": len(titles),
                "passage_count": passage_count,
                "index_path": str(index_path),
                "index_seconds": elapsed_s,
            },
            indent=2,
        )
    )
    return index_path


def _count_indexed_passages(index_path: str) -> int:
    """One entry per indexed passage (post-splitting), keyed by passage id
    -> source article id -- see .ragatouille/.../pid_docid_map.json."""
    pid_docid_map = json.loads((Path(index_path) / "pid_docid_map.json").read_text())
    return len(pid_docid_map)


if __name__ == "__main__":
    build_index()
