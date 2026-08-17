from app.corpus import QUERIES, load_documents


def test_corpus_has_both_doc_types():
    docs = load_documents()
    types = {d["doc_type"] for d in docs}
    assert types == {"code", "text"}
    assert len(docs) > 400  # real corpus target was ~500


def test_corpus_ids_are_unique():
    docs = load_documents()
    ids = [d["id"] for d in docs]
    assert len(ids) == len(set(ids))


def test_query_count_and_category_split():
    assert len(QUERIES) == 20
    assert sum(1 for q in QUERIES if q["category"] == "text") == 10
    assert sum(1 for q in QUERIES if q["category"] == "code") == 10


def test_every_query_ground_truth_id_exists_in_corpus():
    docs = load_documents()
    ids = {d["id"] for d in docs}
    for q in QUERIES:
        assert q["relevant_doc_id"] in ids, q["query"]


def test_query_ground_truth_doc_type_matches_category():
    docs = {d["id"]: d for d in load_documents()}
    for q in QUERIES:
        doc = docs[q["relevant_doc_id"]]
        assert doc["doc_type"] == q["category"], q["query"]
