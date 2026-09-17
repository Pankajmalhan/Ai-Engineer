"""Cheap, network-free tests for BM25Retriever, including the BREAK_RETRIEVAL toggle
this week's "push a deliberately bad change" task relies on."""

from app.corpus import Document
from app.retrieval import BM25Retriever

_DOCS = [
    Document(id="dog", text="The lazy dog sleeps in the sun all afternoon."),
    Document(id="rocket", text="The rocket launch was delayed due to high winds."),
    Document(id="cat", text="A cat quietly naps near the warm dog."),
]


def test_normal_retrieval_returns_most_relevant_first():
    retriever = BM25Retriever(documents=_DOCS, break_retrieval=False)

    top = retriever.retrieve("lazy dog sleeps in the sun", k=1)

    assert top == [_DOCS[0].text]


def test_break_retrieval_returns_least_relevant_first():
    retriever = BM25Retriever(documents=_DOCS, break_retrieval=True)

    top = retriever.retrieve("lazy dog sleeps in the sun", k=1)

    # The rocket document shares no terms with the query -- normal retrieval would
    # always rank it last; BREAK_RETRIEVAL should surface it first instead.
    assert top == [_DOCS[1].text]
