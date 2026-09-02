"""End-to-end demo:

1. Loads real PDF/HTML/DOCX/Markdown fixtures through Unstructured.io into one
   unified document list.
2. Generates a 5000-document synthetic corpus (50 intentional near-duplicates,
   ~15% containing PII), runs it through the full ingestion pipeline, and reports
   the MinHash dedup rate and PII hit rate.
3. Re-runs the same pipeline with a small delta (a handful of documents edited,
   the rest unchanged) to measure the incremental-upsert speedup from the
   content_hash column: unchanged documents are skipped, not re-embedded.

Run with: uv run python -m app.demo
"""

from __future__ import annotations

import random
import time
from pathlib import Path

from app.loaders import load_directory, ocr_available
from app.pii import presidio_available
from app.pipeline import IngestionPipeline
from app.synthetic import generate_corpus
from app.vectorstore import PGVectorStore, is_available

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


def demo_multi_format_loading() -> None:
    print("=" * 70)
    print("1. Multi-format ingestion (Unstructured.io)")
    print("=" * 70)
    if not FIXTURES_DIR.exists():
        print(f"No fixtures at {FIXTURES_DIR} -- run `uv run pytest` once to generate them.")
        return
    docs = load_directory(FIXTURES_DIR)
    by_format: dict[str, int] = {}
    for d in docs:
        by_format[d.format] = by_format.get(d.format, 0) + 1
    for fmt, count in sorted(by_format.items()):
        print(f"  {fmt:>5}: {count} file(s)")
    print(f"  OCR (scanned PDF) available: {ocr_available()} "
          f"{'' if ocr_available() else '(needs tesseract + poppler on PATH)'}")
    print(f"  Presidio (NER PII) available: {presidio_available()}")


def demo_ingestion_and_incremental_upsert() -> None:
    print()
    print("=" * 70)
    print("2. Dedup + PII + incremental upsert on a 5000-document corpus")
    print("=" * 70)
    if not is_available():
        print("Postgres/pgvector not reachable -- run `docker compose up -d` first. Skipping.")
        return

    corpus = generate_corpus(n_base=4950, n_near_duplicates=50, pii_fraction=0.15)
    known_near_dup_ids = {d.id for d in corpus if d.id.startswith("dup-")}
    print(f"  Generated corpus: {len(corpus)} documents (50 intentional near-duplicates)")

    store = PGVectorStore()
    store.clear()
    pipeline = IngestionPipeline(store)

    t0 = time.perf_counter()
    report1 = pipeline.run(corpus, log_metrics=True)
    full_elapsed = time.perf_counter() - t0

    detected_ids = {p.kept_id for p in report1.duplicates} | {p.dropped_id for p in report1.duplicates}
    recall = len(detected_ids & known_near_dup_ids) / len(known_near_dup_ids)

    print(f"  Run 1 (full ingest):")
    print(f"    duplicates dropped : {len(report1.duplicates)} / {report1.total_documents} "
          f"(dedup rate {len(report1.duplicates) / report1.total_documents:.1%})")
    print(f"    of the 50 intentional near-duplicates, {len(detected_ids & known_near_dup_ids)} were "
          f"caught ({recall:.0%} recall) -- MinHash LSH is approximate, not exhaustive; see "
          f"concept.md's Common Pitfalls for why 100% recall isn't guaranteed even above threshold")
    print(f"    documents with PII : {report1.documents_with_pii} "
          f"(hit rate {report1.documents_with_pii / report1.total_documents:.1%} of ingested docs)")
    print(f"    upserted / skipped : {report1.upsert_stats.upserted} / {report1.upsert_stats.skipped}")
    print(f"    wall time          : {full_elapsed:.2f}s")

    # Simulate a real incremental re-ingest: edit a handful of documents, leave the
    # rest byte-identical.
    rng = random.Random(7)
    delta_corpus = [d for d in corpus]
    edited_ids = set()
    for d in rng.sample(delta_corpus, 25):
        d.text = d.text + " Updated for this quarter's policy revision."
        edited_ids.add(d.id)

    t0 = time.perf_counter()
    report2 = pipeline.run(delta_corpus, log_metrics=True)
    incremental_elapsed = time.perf_counter() - t0

    print(f"  Run 2 (25 documents edited, {len(delta_corpus) - 25} unchanged):")
    print(f"    upserted / skipped : {report2.upsert_stats.upserted} / {report2.upsert_stats.skipped}")
    print(f"    wall time          : {incremental_elapsed:.2f}s")
    if incremental_elapsed > 0:
        print(f"    speedup vs. full re-ingest: {full_elapsed / incremental_elapsed:.1f}x")

    store.close()


if __name__ == "__main__":
    demo_multi_format_loading()
    demo_ingestion_and_incremental_upsert()
