from app.data import seed_demo_data
from app.models import Document
from tests.conftest import requires_postgres


@requires_postgres
def test_similarity_search_finds_semantically_close_doc(pg_store):
    pg_store.upsert("test_collection", [
        Document("x1", "Our refund policy allows full refunds within 30 days."),
        Document("x2", "The office is closed on public holidays."),
    ])
    results = pg_store.similarity_search("test_collection", "how do refunds work?", top_k=2)
    assert results[0].id == "x1"
    pg_store.clear("test_collection")


@requires_postgres
def test_upsert_is_idempotent_on_id_and_collection(pg_store):
    pg_store.clear("idempotency_test")
    pg_store.upsert("idempotency_test", [Document("y1", "original text")])
    pg_store.upsert("idempotency_test", [Document("y1", "updated text")])
    docs = pg_store.all_documents("idempotency_test")
    assert len(docs) == 1
    assert docs[0].text == "updated text"
    pg_store.clear("idempotency_test")


@requires_postgres
def test_collections_are_isolated(pg_store):
    pg_store.clear("collection_a")
    pg_store.clear("collection_b")
    pg_store.upsert("collection_a", [Document("z1", "only in a")])
    assert pg_store.all_documents("collection_a")
    assert pg_store.all_documents("collection_b") == []
    pg_store.clear("collection_a")


@requires_postgres
def test_clear_without_collection_removes_everything(pg_store):
    # Destructive against the whole (session-scoped, shared-with-other-tests) store,
    # so reseed the demo data immediately after asserting -- other test modules
    # depend on "docs"/"code" being populated.
    pg_store.upsert("scratch", [Document("s1", "temp")])
    pg_store.clear()
    assert pg_store.all_documents("scratch") == []
    seed_demo_data(pg_store)
