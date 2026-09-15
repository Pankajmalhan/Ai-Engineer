from app.retrieval import BM25Retriever


def test_retrieve_finds_the_relevant_document_top_ranked():
    retriever = BM25Retriever()
    top = retriever.retrieve("How many days for a refund on an annual plan?", k=3)
    assert "refund" in top[0].lower()


def test_retrieve_respects_k():
    retriever = BM25Retriever()
    assert len(retriever.retrieve("rate limit", k=1)) == 1
    assert len(retriever.retrieve("rate limit", k=5)) == 5


def test_retrieve_different_queries_surface_different_top_documents():
    retriever = BM25Retriever()
    refund_top = retriever.retrieve("refund policy annual plan", k=1)[0]
    webhook_top = retriever.retrieve("webhook retry delivery failed", k=1)[0]
    assert refund_top != webhook_top
