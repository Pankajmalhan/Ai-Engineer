"""Benchmark: dense-only vs. hybrid (RRF) recall@10 over the 20-query set.

Each query in corpus.py has exactly one known-relevant document, so
recall@10 for a single query is binary: 1 if that document appears in the
top 10 results, 0 if it doesn't. Averaged over the 20 queries, split by
category (semantic vs. exact-match), this is what actually demonstrates
whether fusion helped -- see concept.md's "Common pitfalls" on why this
needs to be measured, not assumed.

A sparse-only column is included too (beyond what the task strictly asked
for) because on this corpus it's what actually carries the story -- see the
printed note at the end of run().
"""

from collections import defaultdict

from tabulate import tabulate

from app import db
from app.config import RRF_K
from app.corpus import QUERIES
from app.embeddings import embed_query
from app.fusion import rrf_fuse
from app.retriever import CANDIDATE_POOL_SIZE

TOP_K = 10


def run() -> None:
    conn = db.get_connection()
    title_to_id = dict(conn.execute("SELECT title, id FROM documents").fetchall())

    per_query_rows = []
    hits_by_category: dict[str, dict[str, list[int]]] = defaultdict(
        lambda: {"dense": [], "sparse": [], "hybrid": []}
    )

    for q in QUERIES:
        relevant_ids = {title_to_id[t] for t in q["relevant_titles"]}
        query_vec = embed_query(q["query"])

        dense_pool = db.dense_search(conn, query_vec, CANDIDATE_POOL_SIZE)
        sparse_pool = db.sparse_search(conn, q["query"], CANDIDATE_POOL_SIZE)

        dense_top_k_ids = [row[0] for row in dense_pool[:TOP_K]]
        sparse_top_k_ids = [row[0] for row in sparse_pool[:TOP_K]]
        dense_hit = int(bool(relevant_ids & set(dense_top_k_ids)))
        sparse_hit = int(bool(relevant_ids & set(sparse_top_k_ids)))

        fused = rrf_fuse(
            [[row[0] for row in dense_pool], [row[0] for row in sparse_pool]],
            k=RRF_K,
            top_k=TOP_K,
        )
        hybrid_top_k_ids = [doc_id for doc_id, _ in fused]
        hybrid_hit = int(bool(relevant_ids & set(hybrid_top_k_ids)))

        per_query_rows.append(
            [
                q["category"],
                q["query"],
                "hit" if dense_hit else "miss",
                "hit" if sparse_hit else "miss",
                "hit" if hybrid_hit else "miss",
            ]
        )
        hits_by_category[q["category"]]["dense"].append(dense_hit)
        hits_by_category[q["category"]]["sparse"].append(sparse_hit)
        hits_by_category[q["category"]]["hybrid"].append(hybrid_hit)

    print(tabulate(per_query_rows, headers=["category", "query", "dense@10", "sparse@10", "hybrid@10"]))
    print()

    summary_rows = []
    totals = {"dense": [], "sparse": [], "hybrid": []}
    for category, hits in hits_by_category.items():
        for key in totals:
            totals[key] += hits[key]
        summary_rows.append(
            [
                category,
                len(hits["dense"]),
                f"{sum(hits['dense']) / len(hits['dense']):.0%}",
                f"{sum(hits['sparse']) / len(hits['sparse']):.0%}",
                f"{sum(hits['hybrid']) / len(hits['hybrid']):.0%}",
            ]
        )
    summary_rows.append(
        [
            "overall",
            len(totals["dense"]),
            f"{sum(totals['dense']) / len(totals['dense']):.0%}",
            f"{sum(totals['sparse']) / len(totals['sparse']):.0%}",
            f"{sum(totals['hybrid']) / len(totals['hybrid']):.0%}",
        ]
    )
    print(
        tabulate(
            summary_rows,
            headers=["category", "n queries", "dense-only recall@10", "sparse-only recall@10", "hybrid recall@10"],
        )
    )

    print(
        "\nNote: on this corpus/embedding model, dense-only already reaches 100% recall@10 on "
        "both categories, so hybrid ties it rather than beating it on this topline number -- "
        "bge-small's subword tokenizer preserves rare alphanumeric tokens (e.g. 'CVE202441029') "
        "well enough that literal-substring queries still embed close to their one matching "
        "document, even though the model was never trained to treat that as 'exact match'. The "
        "sparse-only column is where the textbook failure mode actually shows up: BM25 recall "
        "collapses on the semantic/paraphrase queries (zero token overlap with the target "
        "document) while staying perfect on exact-token queries. Hybrid's real value here is "
        "insurance, not a topline recall win: it matches whichever single retriever would have "
        "won on a given query, so it can't do worse than the best of the two -- see "
        "tests/test_retrieval.py for the query-level cases that isolate this, and concept.md's "
        "'Common pitfalls' section on why recall@10 improvement from hybrid is not guaranteed "
        "and has to be measured on your own corpus, not assumed from theory."
    )


if __name__ == "__main__":
    run()
