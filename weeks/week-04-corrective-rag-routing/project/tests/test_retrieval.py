from app.data import CODE_COLLECTION, DOCS_COLLECTION
from app.retrieval import hybrid_search
from tests.conftest import requires_postgres


@requires_postgres
def test_hybrid_search_ranks_matching_doc_first(pg_store):
    results = hybrid_search("What is our refund policy for annual plans?", pg_store, DOCS_COLLECTION)
    assert results[0].id == "d1"


@requires_postgres
def test_hybrid_search_respects_top_k(pg_store):
    results = hybrid_search("company policy", pg_store, DOCS_COLLECTION, top_k=2)
    assert len(results) == 2


@requires_postgres
def test_hybrid_search_empty_collection_returns_empty(pg_store):
    assert hybrid_search("anything", pg_store, "nonexistent_collection") == []


@requires_postgres
def test_hybrid_search_ranks_matching_code_snippet_first(pg_store):
    results = hybrid_search(
        "Why does getUserById() throw a NullPointerException?", pg_store, CODE_COLLECTION
    )
    assert results[0].id == "c2"


@requires_postgres
def test_hybrid_search_code_route_favors_exact_identifier_match(pg_store):
    results = hybrid_search(
        "merge conflict git", pg_store, CODE_COLLECTION, bm25_weight=2.0, dense_weight=1.0
    )
    assert results[0].id == "c3"
