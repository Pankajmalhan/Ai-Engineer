"""A/B test: hybrid-only vs. hybrid+Cohere-rerank vs. hybrid+BGE-rerank,
over the Week 1 20-query benchmark set, measuring NDCG@10 lift and latency
added by each reranker.

Stage 1 (retriever.hybrid_candidates) runs once per query and its
RERANK_POOL_SIZE-candidate output is shared across all three columns, so the
comparison isolates Stage 2's effect -- every reranker (and the no-rerank
baseline) sees exactly the same candidate pool, in the same order, for a
given query.

Cohere is included only if COHERE_API_KEY is set (see .env.example); if
it's missing, that column is skipped with a printed note instead of
crashing the run -- this script always completes end-to-end whether or not
you've set up a Cohere account. BGE always runs locally; it downloads
~1.1GB on first use (cached under ~/.cache/huggingface after that).
"""

import json
import time
from collections import defaultdict
from pathlib import Path

from tabulate import tabulate

from app import db
from app.config import FINAL_TOP_K, RERANK_POOL_SIZE
from app.corpus import QUERIES
from app.metrics import ndcg_at_k, recall_at_k
from app.rerankers import BGEReranker, CohereReranker, NoOpReranker, RerankerUnavailable
from app.retriever import hybrid_candidates

RESULTS_PATH = Path(__file__).parent.parent / "data" / "benchmark_results.json"


def _build_rerankers() -> list:
    rerankers = [NoOpReranker()]

    try:
        rerankers.append(CohereReranker())
    except RerankerUnavailable as exc:
        print(f"[skip] Cohere reranker: {exc}\n")

    print("Loading BGE reranker (downloads the model on first run)...")
    rerankers.append(BGEReranker())

    return rerankers


def run() -> None:
    conn = db.get_connection()
    title_to_id = dict(conn.execute("SELECT title, id FROM documents").fetchall())

    rerankers = _build_rerankers()

    per_query_rows = []
    per_query_json = []
    metrics_by_reranker: dict[str, dict[str, list]] = {
        r.name: {"ndcg": [], "recall": [], "latency_ms": []} for r in rerankers
    }

    for q in QUERIES:
        relevant_ids = {title_to_id[t] for t in q["relevant_titles"]}
        candidates = hybrid_candidates(conn, q["query"], pool_size=RERANK_POOL_SIZE)

        row = [q["category"], q["query"]]
        query_result = {
            "query": q["query"],
            "category": q["category"],
            "rerankers": {},
        }

        for reranker in rerankers:
            start = time.perf_counter()
            results = reranker.rerank(q["query"], candidates, top_n=FINAL_TOP_K)
            latency_ms = (time.perf_counter() - start) * 1000

            ranked_ids = [r.doc_id for r in results]
            ndcg = ndcg_at_k(ranked_ids, relevant_ids, k=FINAL_TOP_K)
            recall = recall_at_k(ranked_ids, relevant_ids, k=FINAL_TOP_K)

            metrics_by_reranker[reranker.name]["ndcg"].append(ndcg)
            metrics_by_reranker[reranker.name]["recall"].append(recall)
            metrics_by_reranker[reranker.name]["latency_ms"].append(latency_ms)

            row.append(f"{ndcg:.2f}")
            query_result["rerankers"][reranker.name] = {
                "ndcg_at_10": ndcg,
                "recall_at_10": recall,
                "latency_ms": latency_ms,
            }

        per_query_rows.append(row)
        per_query_json.append(query_result)

    print(
        tabulate(
            per_query_rows,
            headers=["category", "query", *[f"{r.name} ndcg@10" for r in rerankers]],
        )
    )
    print()

    summary_rows = []
    summary_json = {}
    for reranker in rerankers:
        m = metrics_by_reranker[reranker.name]
        n = len(m["ndcg"])
        mean_ndcg = sum(m["ndcg"]) / n
        mean_recall = sum(m["recall"]) / n
        mean_latency = sum(m["latency_ms"]) / n
        summary_rows.append(
            [reranker.name, n, f"{mean_ndcg:.3f}", f"{mean_recall:.0%}", f"{mean_latency:.1f} ms"]
        )
        summary_json[reranker.name] = {
            "mean_ndcg_at_10": mean_ndcg,
            "mean_recall_at_10": mean_recall,
            "mean_latency_ms": mean_latency,
        }

    print(
        tabulate(
            summary_rows,
            headers=["reranker", "n queries", "mean ndcg@10", "recall@10", "mean latency added"],
        )
    )

    baseline_ndcg = summary_json[NoOpReranker.name]["mean_ndcg_at_10"]
    print(f"\nBaseline (hybrid only, no rerank): NDCG@10 = {baseline_ndcg:.3f}")
    for reranker in rerankers:
        if reranker.name == NoOpReranker.name:
            continue
        s = summary_json[reranker.name]
        lift = s["mean_ndcg_at_10"] - baseline_ndcg
        print(
            f"{reranker.name}: NDCG@10 = {s['mean_ndcg_at_10']:.3f} "
            f"({'+' if lift >= 0 else ''}{lift:.3f} vs. baseline), "
            f"+{s['mean_latency_ms']:.1f} ms/query added"
        )

    RESULTS_PATH.parent.mkdir(exist_ok=True)
    RESULTS_PATH.write_text(
        json.dumps(
            {
                "rerank_pool_size": RERANK_POOL_SIZE,
                "final_top_k": FINAL_TOP_K,
                "summary": summary_json,
                "per_query": per_query_json,
            },
            indent=2,
        )
    )
    print(f"\nWrote {RESULTS_PATH}")


if __name__ == "__main__":
    run()
