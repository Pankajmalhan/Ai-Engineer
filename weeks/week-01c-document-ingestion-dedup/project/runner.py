"""Standalone debug script for app/pipeline.py -- runs hardcoded raw documents
(a clean doc, a PII doc, and a near-duplicate pair) through the real
IngestionPipeline end to end: hash -> redact -> dedup -> incremental upsert.

Needs Postgres/pgvector reachable at DATABASE_URL (`docker compose up -d` in this
directory first) -- prints a clear message and exits if it isn't.

Run with: uv run python runner.py
"""

from app.models import RawDocument
from app.pipeline import IngestionPipeline
from app.vectorstore import PGVectorStore, is_available

BASE_TEXT = (
    "Our refund policy allows a full refund within thirty days of purchase for "
    "annual plans, and a prorated refund for any time used beyond that window."
)

RAW_DOCS = [
    RawDocument(id="clean", source_path="mem://clean", format="md", text=BASE_TEXT),
    RawDocument(
        id="near-dup-of-clean",
        source_path="mem://near-dup-of-clean",
        format="md",
        text=BASE_TEXT + " Reviewed quarterly.",
    ),
    RawDocument(
        id="pii-doc",
        source_path="mem://pii-doc",
        format="md",
        text=(
            "Please contact Priya Chen at priya.chen@example.com or 415-555-0199 "
            "regarding employee ID EM-482913."
        ),
    ),
]


def print_report(label: str, report) -> None:
    print(f"\n--- {label} ---")
    print(f"  total_documents     : {report.total_documents}")
    print(f"  unchanged_documents : {report.unchanged_documents}")
    print(f"  duplicates          : {[(d.dropped_id, d.kept_id, round(d.jaccard, 3)) for d in report.duplicates]}")
    print(f"  pii_hits            : {report.pii_hits}")
    print(f"  documents_with_pii  : {report.documents_with_pii}")
    print(f"  upsert_stats        : upserted={report.upsert_stats.upserted} skipped={report.upsert_stats.skipped}")


def print_store_state(store: PGVectorStore) -> None:
    print("\n--- documents table (post-redaction content actually indexed) ---")
    rows = store._conn.execute("SELECT id, content FROM documents ORDER BY id").fetchall()
    for doc_id, content in rows:
        print(f"  [{doc_id}] {content!r}")

    print("\n--- skipped_documents table (dropped as near-duplicates) ---")
    rows = store._conn.execute("SELECT id FROM skipped_documents ORDER BY id").fetchall()
    for (doc_id,) in rows:
        print(f"  [{doc_id}]")


def main() -> None:
    if not is_available():
        print(
            "Postgres/pgvector not reachable at DATABASE_URL -- run `docker compose "
            "up -d` in this directory first, then re-run this script."
        )
        return

    store = PGVectorStore()
    store.clear()  # start from a clean slate so this debug run is deterministic
    pipeline = IngestionPipeline(store)

    report1 = pipeline.run(RAW_DOCS, log_metrics=True)
    print_report("Run 1 (first ingestion)", report1)
    print_store_state(store)

    report2 = pipeline.run(RAW_DOCS, log_metrics=True)
    print_report("Run 2 (same input, nothing changed)", report2)

    store.close()


if __name__ == "__main__":
    main()
