"""Weekly task: profile memory/index size -- ColBERT stores one 128-dim
vector per *token*, not per document, and this script measures what that
actually costs on disk versus the single-vector bi-encoder baseline, over
the *same* corpus.

Three numbers, not one, because "per-token storage" on its own conflates
two different things:
  1. What raw, uncompressed per-token storage would cost (passages x avg
     tokens x 128 dims x 4 bytes) -- the naive number people usually quote.
  2. What PLAID's residual compression (see concept.md) actually brings
     that down to on disk, measured directly from the index directory.
  3. What the bi-encoder baseline actually costs on disk, for the same
     passages -- one 384-dim fp32 vector each.
"""

import json
from pathlib import Path

from app.config import BIENCODER_MODEL, INDEX_NAME

DATA_DIR = Path(__file__).parent.parent / "data"
INDEX_DIR = Path(__file__).parent.parent / ".ragatouille" / "colbert" / "indexes" / INDEX_NAME

COLBERT_DIM = 128
COLBERT_DTYPE_BYTES = 4  # fp32, for the "uncompressed" estimate only


def _dir_size_bytes(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def _avg_tokens_per_passage() -> tuple[int, float]:
    doclens_files = sorted(INDEX_DIR.glob("doclens.*.json"))
    lengths = []
    for f in doclens_files:
        lengths.extend(json.loads(f.read_text()))
    return len(lengths), (sum(lengths) / len(lengths) if lengths else 0.0)


def run() -> None:
    if not INDEX_DIR.exists():
        raise FileNotFoundError(f"No index at {INDEX_DIR} -- run `uv run python -m app.index` first.")

    baseline_path = DATA_DIR / "baseline_embeddings.npy"
    if not baseline_path.exists():
        raise FileNotFoundError("No baseline embeddings -- run `uv run python -m app.baseline` first.")

    passage_count, avg_tokens = _avg_tokens_per_passage()
    colbert_disk_bytes = _dir_size_bytes(INDEX_DIR)
    baseline_disk_bytes = baseline_path.stat().st_size

    uncompressed_colbert_bytes = passage_count * avg_tokens * COLBERT_DIM * COLBERT_DTYPE_BYTES

    print(f"Corpus: {passage_count} passages, {avg_tokens:.1f} tokens/passage on average\n")

    print(f"{'':32}{'total':>14}{'bytes/passage':>18}")
    print(f"{'ColBERT (uncompressed est.)':32}{uncompressed_colbert_bytes / 1e6:>11.1f} MB{uncompressed_colbert_bytes / passage_count:>15,.0f} B")
    print(f"{'ColBERT/PLAID (actual, on disk)':32}{colbert_disk_bytes / 1e6:>11.1f} MB{colbert_disk_bytes / passage_count:>15,.0f} B")
    print(f"{'Bi-encoder (' + BIENCODER_MODEL.split('/')[-1] + ')':32}{baseline_disk_bytes / 1e6:>11.1f} MB{baseline_disk_bytes / passage_count:>15,.0f} B")

    compression_ratio = uncompressed_colbert_bytes / colbert_disk_bytes
    blowup_vs_biencoder = colbert_disk_bytes / baseline_disk_bytes
    print(f"\nPLAID's residual compression: {compression_ratio:.1f}x smaller than uncompressed per-token storage")
    print(f"ColBERT/PLAID index is {blowup_vs_biencoder:.1f}x the size of the single-vector bi-encoder index, for the same {passage_count} passages")

    DATA_DIR.mkdir(exist_ok=True)
    (DATA_DIR / "index_profile.json").write_text(
        json.dumps(
            {
                "passage_count": passage_count,
                "avg_tokens_per_passage": avg_tokens,
                "colbert_uncompressed_estimate_bytes": uncompressed_colbert_bytes,
                "colbert_plaid_actual_bytes": colbert_disk_bytes,
                "biencoder_actual_bytes": baseline_disk_bytes,
                "plaid_compression_ratio": compression_ratio,
                "colbert_vs_biencoder_ratio": blowup_vs_biencoder,
            },
            indent=2,
        )
    )
    print(f"\nWrote {DATA_DIR / 'index_profile.json'}")


if __name__ == "__main__":
    run()
