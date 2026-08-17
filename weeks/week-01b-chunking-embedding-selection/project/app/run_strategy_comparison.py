"""Part 1: holds the embedding model fixed and compares all 6 chunking
strategies against each other, measured with NDCG@10.

Fixed model: nomic-ai/modernbert-embed-base. Not arbitrary -- it's the one
model in the shortlist with a real long context window (8192 tokens), so
it's the only one of the three that lets late_chunking actually do what
late chunking is for (attend over the whole document before pooling). Using
a short-context model here would structurally handicap late_chunking before
the comparison even starts.
"""

import json
import time
from pathlib import Path

from tabulate import tabulate

from app.corpus import QUERIES, load_documents
from app.chunkers import STRATEGIES
from app.metrics import ndcg_at_k, recall_at_k
from app.retrieval import build_index, search
from app.wandb_logging import log_run

FIXED_MODEL = "nomic-ai/modernbert-embed-base"
RESULTS_PATH = Path(__file__).parent.parent / "data" / "part1_strategy_comparison.json"


def run() -> None:
    docs = load_documents()
    queries = [q["query"] for q in QUERIES]
    relevant_ids = [q["relevant_doc_id"] for q in QUERIES]
    categories = [q["category"] for q in QUERIES]

    per_strategy_rows = []
    results = []

    for strategy in STRATEGIES:
        t0 = time.time()
        index = build_index(docs, strategy, FIXED_MODEL)
        retrieved = search(index, queries, FIXED_MODEL, k=10)
        elapsed = time.time() - t0

        ndcgs, recalls = [], []
        for ret, rel_id in zip(retrieved, relevant_ids):
            rel_count = index.relevant_chunk_count(rel_id)
            ndcgs.append(ndcg_at_k(ret, rel_id, rel_count, k=10))
            recalls.append(recall_at_k(ret, rel_id, k=10))

        mean_ndcg = sum(ndcgs) / len(ndcgs)
        mean_recall = sum(recalls) / len(recalls)
        n_chunks = len(index.chunks)

        per_strategy_rows.append(
            [strategy, n_chunks, f"{mean_recall:.0%}", f"{mean_ndcg:.4f}", f"{elapsed:.1f}s"]
        )
        results.append(
            {
                "strategy": strategy,
                "model": FIXED_MODEL,
                "n_chunks": n_chunks,
                "recall_at_10": mean_recall,
                "ndcg_at_10": mean_ndcg,
                "seconds": elapsed,
                "per_query": [
                    {"query": q, "category": c, "ndcg_at_10": n, "recall_at_10": r}
                    for q, c, n, r in zip(queries, categories, ndcgs, recalls)
                ],
            }
        )
        log_run(
            chunking_strategy=strategy,
            embedding_model=FIXED_MODEL,
            metrics={"ndcg_at_10": mean_ndcg, "recall_at_10": mean_recall, "n_chunks": n_chunks},
            part="strategy_comparison",
        )
        print(f"done: {strategy:16} ndcg@10={mean_ndcg:.4f} recall@10={mean_recall:.0%} chunks={n_chunks} ({elapsed:.1f}s)")

    print()
    print(tabulate(per_strategy_rows, headers=["strategy", "n_chunks", "recall@10", "ndcg@10", "time"]))

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(results, indent=2))
    print(f"\nwritten to {RESULTS_PATH}")


if __name__ == "__main__":
    run()
