import json

import httpx

from app.retrieval import BM25Retriever
from evals.eval_endpoint_parity import check_health, check_retrieval_parity


def _client_with(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_check_health_passes_on_ok_status():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "ok"})

    assert check_health("http://example.test", _client_with(handler)) is True


def test_check_health_fails_on_bad_status():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "degraded"})

    assert check_health("http://example.test", _client_with(handler)) is False


def test_check_retrieval_parity_passes_when_remote_matches_local():
    retriever = BM25Retriever()

    def handler(request: httpx.Request) -> httpx.Response:
        question = json.loads(request.content)["question"]
        doc_ids = [d.id for d in retriever.retrieve(question, k=3)]
        return httpx.Response(200, json={"answer": "x", "retrieved_contexts": [], "retrieved_doc_ids": doc_ids})

    assert check_retrieval_parity("http://example.test", _client_with(handler)) is True


def test_check_retrieval_parity_fails_when_remote_diverges():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"answer": "x", "retrieved_contexts": [], "retrieved_doc_ids": ["wrong-doc"]})

    assert check_retrieval_parity("http://example.test", _client_with(handler)) is False
