"""Part 2: crosses all 3 shortlisted embedding models with all 6 chunking
strategies (18 combinations), measures recall@10 for each, and picks the
winner -- which gets hard-coded into config.py as the pipeline default for
subsequent weeks (update_defaults()).

Primary metric is recall@10, per the task. NDCG@10 is also recorded (same
per_query data Part 1 uses) since recall@10 alone can't break a tie between
two combinations that both find the right document but rank it very
differently -- see week 1's concept.md on why rank-blind recall isn't the
whole story.
"""

import json
import time
from pathlib import Path

from tabulate import tabulate

from app.chunkers import STRATEGIES
from app.corpus import QUERIES, load_documents
from app.embeddings import MODELS
from app.metrics import ndcg_at_k, recall_at_k
from app.retrieval import build_index, search
from app.wandb_logging import log_run

RESULTS_PATH = Path(__file__).parent.parent / "data" / "part2_model_strategy_grid.json"
CONFIG_PATH = Path(__file__).parent / "config.py"


def run() -> dict:
    docs = load_documents()
    queries = [q["query"] for q in QUERIES]
    relevant_ids = [q["relevant_doc_id"] for q in QUERIES]

    grid_rows = []
    results = []

    for model_name in MODELS:
        for strategy in STRATEGIES:
            t0 = time.time()
            index = build_index(docs, strategy, model_name)
            retrieved = search(index, queries, model_name, k=10)
            elapsed = time.time() - t0

            recalls, ndcgs = [], []
            for ret, rel_id in zip(retrieved, relevant_ids):
                rel_count = index.relevant_chunk_count(rel_id)
                recalls.append(recall_at_k(ret, rel_id, k=10))
                ndcgs.append(ndcg_at_k(ret, rel_id, rel_count, k=10))

            mean_recall = sum(recalls) / len(recalls)
            mean_ndcg = sum(ndcgs) / len(ndcgs)
            n_chunks = len(index.chunks)

            grid_rows.append(
                [model_name, strategy, n_chunks, f"{mean_recall:.0%}", f"{mean_ndcg:.4f}", f"{elapsed:.1f}s"]
            )
            results.append(
                {
                    "model": model_name,
                    "strategy": strategy,
                    "n_chunks": n_chunks,
                    "recall_at_10": mean_recall,
                    "ndcg_at_10": mean_ndcg,
                    "seconds": elapsed,
                }
            )
            log_run(
                chunking_strategy=strategy,
                embedding_model=model_name,
                metrics={"recall_at_10": mean_recall, "ndcg_at_10": mean_ndcg, "n_chunks": n_chunks},
                part="model_strategy_grid",
            )
            print(
                f"done: model={model_name:35} strategy={strategy:16} "
                f"recall@10={mean_recall:.0%} ndcg@10={mean_ndcg:.4f} chunks={n_chunks} ({elapsed:.1f}s)"
            )

    print()
    print(tabulate(grid_rows, headers=["model", "strategy", "n_chunks", "recall@10", "ndcg@10", "time"]))

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(results, indent=2))
    print(f"\nwritten to {RESULTS_PATH}")

    winner = max(results, key=lambda r: (r["recall_at_10"], r["ndcg_at_10"]))
    print(f"\nwinner: {winner['model']} + {winner['strategy']} "
          f"(recall@10={winner['recall_at_10']:.0%}, ndcg@10={winner['ndcg_at_10']:.4f})")
    return winner


def update_defaults(winner: dict) -> None:
    note = (
        f"Set from Part 2 benchmark: {winner['model']} + {winner['strategy']} "
        f"scored recall@10={winner['recall_at_10']:.0%}, ndcg@10={winner['ndcg_at_10']:.4f} "
        f"on the 20-query set (see data/part2_model_strategy_grid.json)."
    )
    CONFIG_PATH.write_text(
        '"""Pipeline defaults. DEFAULT_CHUNKING_STRATEGY / DEFAULT_EMBEDDING_MODEL are\n'
        "set from Part 2's measured winner (see run_model_strategy_grid.py and\n"
        "data/part2_model_strategy_grid.json) -- this is the \"hard-code the winning\n"
        'combination as the pipeline default for all subsequent Q1 weeks" task.\n'
        "Do not hand-edit these without re-running the benchmark; if you change the\n"
        "corpus or query set, re-run Part 2 and update both constants + WINNER_NOTE\n"
        'together so they can\'t drift out of sync.\n"""\n\n'
        f'DEFAULT_CHUNKING_STRATEGY = "{winner["strategy"]}"\n'
        f'DEFAULT_EMBEDDING_MODEL = "{winner["model"]}"\n'
        f'WINNER_NOTE = "{note}"\n'
    )
    print(f"\nconfig.py updated:\n  DEFAULT_CHUNKING_STRATEGY = {winner['strategy']!r}\n"
          f"  DEFAULT_EMBEDDING_MODEL = {winner['model']!r}")


if __name__ == "__main__":
    winner = run()
    update_defaults(winner)
