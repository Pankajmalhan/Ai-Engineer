from app.models import ProcessedDocument
from tests.conftest import requires_postgres


def _docs(n: int, prefix: str = "d") -> list[ProcessedDocument]:
    return [
        ProcessedDocument(id=f"{prefix}{i}", source_path=f"mem://{prefix}{i}", format="md", text=f"document number {i} about refunds")
        for i in range(n)
    ]


@requires_postgres
def test_first_upsert_writes_every_document(pg_store):
    docs = _docs(5)
    stats = pg_store.incremental_upsert(docs)
    assert stats.upserted == 5
    assert stats.skipped == 0
    assert pg_store.count() == 5


@requires_postgres
def test_second_upsert_with_unchanged_content_skips_everything(pg_store):
    docs = _docs(5, prefix="u")
    pg_store.incremental_upsert(docs)
    stats = pg_store.incremental_upsert(docs)
    assert stats.upserted == 0
    assert stats.skipped == 5


@requires_postgres
def test_only_changed_documents_are_re_upserted(pg_store):
    docs = _docs(10, prefix="c")
    pg_store.incremental_upsert(docs)

    docs[3].text = "this document's content actually changed"
    docs[7].text = "so did this one"
    from app.models import content_hash

    docs[3].hash = content_hash(docs[3].text)
    docs[7].hash = content_hash(docs[7].text)

    stats = pg_store.incremental_upsert(docs)
    assert stats.upserted == 2
    assert stats.skipped == 8


@requires_postgres
def test_content_hash_is_stored_and_used_for_the_diff(pg_store):
    docs = _docs(3, prefix="h")
    pg_store.incremental_upsert(docs)
    stored = pg_store.existing_hashes([d.id for d in docs])
    assert stored == {d.id: d.hash for d in docs}
