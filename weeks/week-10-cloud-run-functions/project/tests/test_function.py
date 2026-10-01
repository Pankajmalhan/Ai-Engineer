"""Exercises the deployed function's exact entry point (`main.rag_chat`) through
functions-framework's own test harness -- not a hand-rolled Flask app -- so this test
would catch a broken `--function` target before it ever reaches `gcloud run deploy`.
"""

from __future__ import annotations

import functions_framework
from app.llm import GenerationResult
from app.pipeline import RAGPipeline


def _make_client(monkeypatch):
    def _fake_generate(question: str, contexts: list[str]) -> GenerationResult:
        return GenerationResult(answer=f"stub answer for: {question}", input_tokens=1, output_tokens=1)

    monkeypatch.setattr("app.pipeline.generate_answer", _fake_generate)
    monkeypatch.setattr("main._pipeline", RAGPipeline())

    import main

    app = functions_framework.create_app(target="rag_chat", source=main.__file__)
    return app.test_client()


def test_health_check_is_a_plain_get(monkeypatch):
    client = _make_client(monkeypatch)
    response = client.get("/")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_missing_question_is_a_400(monkeypatch):
    client = _make_client(monkeypatch)
    response = client.post("/", json={})
    assert response.status_code == 400


def test_chat_returns_answer_and_contexts(monkeypatch):
    client = _make_client(monkeypatch)
    response = client.post("/", json={"question": "What's the refund window for annual plans?"})
    assert response.status_code == 200
    body = response.get_json()
    assert body["answer"].startswith("stub answer for:")
    assert body["retrieved_contexts"]
    assert body["retrieved_doc_ids"]
