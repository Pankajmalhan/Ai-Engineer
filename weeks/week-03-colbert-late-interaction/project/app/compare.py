"""This week's actual A/B: for every MULTIHOP_QUERIES question, run it
through both the ColBERT/PLAID index (token-level MaxSim) and the
single-vector bi-encoder baseline (cosine similarity), and check whether
each side's top-k results land on one of the query's relevant_titles.

The two scores are never compared by raw magnitude (see concept.md's
worked example for why -- MaxSim is a sum over query tokens, cosine is a
single bounded number). What's compared is hit@k -- did the *right*
articles make it into each side's top k -- since that's the thing a
compositional query actually stresses.
"""

import json
from pathlib import Path

from ragatouille import RAGPretrainedModel
from tabulate import tabulate

from app.baseline import load_baseline, search_baseline
from app.config import INDEX_NAME, TOP_K
from app.corpus import MULTIHOP_QUERIES

RESULTS_PATH = Path(__file__).parent.parent / "data" / "compare_results.json"


def _hits(results: list[dict], relevant_titles: set[str]) -> int:
    return sum(1 for r in results if r["document_id"] in relevant_titles)


def run() -> None:
    RAG = RAGPretrainedModel.from_index(f".ragatouille/colbert/indexes/{INDEX_NAME}")
    embeddings, passages = load_baseline()

    rows = []
    per_query = []
    colbert_hit_queries = 0
    baseline_hit_queries = 0

    for q in MULTIHOP_QUERIES:
        relevant_titles = set(q["relevant_titles"])

        colbert_results = RAG.search(q["query"], k=TOP_K)
        baseline_results = search_baseline(q["query"], TOP_K, embeddings, passages)

        colbert_hits = _hits(colbert_results, relevant_titles)
        baseline_hits = _hits(baseline_results, relevant_titles)
        colbert_hit_queries += colbert_hits > 0
        baseline_hit_queries += baseline_hits > 0

        rows.append(
            [
                q["query"][:60] + ("..." if len(q["query"]) > 60 else ""),
                f"{colbert_hits}/{len(relevant_titles)} titles",
                f"{baseline_hits}/{len(relevant_titles)} titles",
            ]
        )
        per_query.append(
            {
                "query": q["query"],
                "note": q["note"],
                "relevant_titles": q["relevant_titles"],
                "colbert": [
                    {"rank": r["rank"], "score": r["score"], "document_id": r["document_id"]}
                    for r in colbert_results
                ],
                "baseline": [
                    {"rank": r["rank"], "score": r["score"], "document_id": r["document_id"]}
                    for r in baseline_results
                ],
            }
        )

    print(tabulate(rows, headers=["multi-hop query", f"ColBERT hits@{TOP_K}", f"bi-encoder hits@{TOP_K}"]))
    n = len(MULTIHOP_QUERIES)
    print(
        f"\nQueries with >=1 relevant title in top {TOP_K}: "
        f"ColBERT {colbert_hit_queries}/{n}, bi-encoder {baseline_hit_queries}/{n}"
    )

    RESULTS_PATH.parent.mkdir(exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(per_query, indent=2))
    print(f"\nWrote {RESULTS_PATH}")


if __name__ == "__main__":
    run()
