from app.models import RawDocument
from app.pii import RegexPIIRedactor
from app.pipeline import IngestionPipeline
from tests.conftest import requires_postgres

BASE_TEXT = (
    "Our refund policy allows a full refund within thirty days of purchase for "
    "annual plans, and a prorated refund for any time used beyond that window, "
    "provided the request is submitted through the billing portal. Exceptions are "
    "reviewed case by case by the billing team, and approved refunds are issued "
    "to the original payment method within five business days of approval."
)
NEAR_DUPLICATE_TEXT = BASE_TEXT + " Last reviewed this quarter."
PII_TEXT = "Contact Priya Chen at priya.chen@example.com about her refund."


@requires_postgres
def test_pipeline_drops_duplicates_redacts_pii_and_upserts_only_unique(pg_store):
    raw_docs = [
        RawDocument(id="a", source_path="mem://a", format="md", text=BASE_TEXT),
        RawDocument(id="b", source_path="mem://b", format="md", text=NEAR_DUPLICATE_TEXT),
        RawDocument(id="c", source_path="mem://c", format="md", text=PII_TEXT),
    ]
    pipeline = IngestionPipeline(pg_store, redactor=RegexPIIRedactor())
    report = pipeline.run(raw_docs)

    assert report.total_documents == 3
    assert len(report.duplicates) == 1
    assert report.duplicates[0].dropped_id == "b"
    assert report.documents_with_pii == 1
    assert report.pii_hits >= 1
    assert report.upsert_stats.upserted == 2  # "a" and "c", "b" dropped as a near-dup

    stored_ids = set(pg_store.all_ids())
    assert stored_ids == {"a", "c"}


@requires_postgres
def test_pii_is_redacted_before_it_reaches_the_vector_store(pg_store):
    raw_docs = [RawDocument(id="pii-doc", source_path="mem://pii-doc", format="md", text=PII_TEXT)]
    pipeline = IngestionPipeline(pg_store, redactor=RegexPIIRedactor())
    pipeline.run(raw_docs)

    rows = pg_store._conn.execute("SELECT content FROM documents WHERE id = %s", ("pii-doc",)).fetchall()
    assert "priya.chen@example.com" not in rows[0][0]
    assert "<EMAIL_ADDRESS>" in rows[0][0]


@requires_postgres
def test_rerunning_the_pipeline_with_no_changes_skips_every_upsert(pg_store):
    raw_docs = [RawDocument(id="static", source_path="mem://static", format="md", text=BASE_TEXT)]
    pipeline = IngestionPipeline(pg_store, redactor=RegexPIIRedactor())
    pipeline.run(raw_docs)
    report2 = pipeline.run(raw_docs)
    assert report2.upsert_stats.upserted == 0
    assert report2.upsert_stats.skipped == 1


@requires_postgres
def test_a_dropped_duplicate_stays_dropped_on_a_later_unchanged_rerun(pg_store):
    """A dropped-duplicate id has no row in `documents` at all. Without persisting
    the skip decision (skipped_documents), a later run with the exact same raw input
    would see "no stored hash for this id" and treat it as new, re-redacting it and
    -- since dedup only compares within that run's batch -- upserting it as a
    false-unique if its near-dup source isn't in that batch too."""
    raw_docs = [
        RawDocument(id="a", source_path="mem://a", format="md", text=BASE_TEXT),
        RawDocument(id="b", source_path="mem://b", format="md", text=NEAR_DUPLICATE_TEXT),
    ]
    pipeline = IngestionPipeline(pg_store, redactor=RegexPIIRedactor())
    pipeline.run(raw_docs)
    assert set(pg_store.all_ids()) == {"a"}

    # Second run passes only the previously-dropped duplicate, unchanged, with no
    # near-dup source present in this batch at all.
    report2 = pipeline.run([raw_docs[1]])
    assert report2.upsert_stats.upserted == 0
    assert report2.upsert_stats.skipped == 1
    assert set(pg_store.all_ids()) == {"a"}
