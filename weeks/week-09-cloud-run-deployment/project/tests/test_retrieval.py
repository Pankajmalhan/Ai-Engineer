from app.corpus import CORPUS
from app.retrieval import BM25Retriever


def test_retrieve_returns_documents_with_ids():
    retriever = BM25Retriever()
    docs = retriever.retrieve("refund window annual plan", k=3)
    assert len(docs) == 3
    assert all(hasattr(d, "id") and hasattr(d, "text") for d in docs)


def test_retrieve_ranks_relevant_doc_first():
    retriever = BM25Retriever()
    docs = retriever.retrieve("How many days for a refund on an annual plan?", k=1)
    assert docs[0].id == "refunds"


def test_top_score_is_higher_for_relevant_query_than_nonsense():
    retriever = BM25Retriever()
    relevant = retriever.top_score("What's the refund window for annual plans?")
    nonsense = retriever.top_score("zzz qux flibbertigibbet")
    assert relevant > nonsense


def test_corpus_fixture_unchanged_shape():
    assert len(CORPUS) == 8
