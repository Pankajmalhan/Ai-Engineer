"""NoOpReranker and the RerankerUnavailable guard are pure/free and always
run. CohereReranker's real API call is skipped without COHERE_API_KEY (see
.env.example) rather than failing the suite. BGEReranker's test hits the
real local cross-encoder model -- not mocked, so it catches real
sentence-transformers API drift -- and downloads the model on first run
(cached under ~/.cache/huggingface after that, same as fastembed in Week
1's tests)."""

import os

import pytest

from app.rerankers import BGEReranker, CohereReranker, NoOpReranker, RerankerUnavailable

CANDIDATES = [
    (1, "python-gil", "The Python Global Interpreter Lock prevents multiple native threads from executing Python bytecode simultaneously."),
    (2, "sourdough", "Sourdough bread needs a highly active starter and a long, cold overnight proof."),
    (3, "python-async", "Python's asyncio module lets a single thread interleave many I/O-bound coroutines cooperatively."),
]


def test_noop_reranker_preserves_hybrid_order_and_truncates():
    result = NoOpReranker().rerank("anything", CANDIDATES, top_n=2)

    assert [r.doc_id for r in result] == [1, 2]


def test_cohere_reranker_raises_without_api_key(monkeypatch):
    monkeypatch.delenv("COHERE_API_KEY", raising=False)

    with pytest.raises(RerankerUnavailable):
        CohereReranker(api_key=None)


@pytest.mark.skipif(
    not os.environ.get("COHERE_API_KEY"),
    reason="COHERE_API_KEY not set -- see .env.example",
)
def test_cohere_reranker_ranks_the_more_relevant_python_doc_first():
    reranker = CohereReranker()

    result = reranker.rerank(
        "how does Python's GIL affect threading?", CANDIDATES, top_n=3
    )

    assert result[0].doc_id == 1


def test_bge_reranker_ranks_the_more_relevant_python_doc_first():
    reranker = BGEReranker()

    result = reranker.rerank(
        "how does Python's GIL affect threading?", CANDIDATES, top_n=3
    )

    assert result[0].doc_id == 1
    assert len(result) == 3
    # scores should be strictly descending -- that's what "ranked" means
    assert result[0].score >= result[1].score >= result[2].score
