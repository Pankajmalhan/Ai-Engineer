from fastapi.testclient import TestClient

import app.main as main_module
from app.llm import GenerationResult
from app.pipeline import RAGPipeline
from app.retrieval import BM25Retriever


def _stub_generate(question: str, contexts: list[str]) -> GenerationResult:
    return GenerationResult(answer=f"stub answer for: {question}", input_tokens=1, output_tokens=1)


def test_health():
    client = TestClient(main_module.app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_returns_answer_and_contexts(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "")
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    monkeypatch.setattr("app.pipeline.generate_answer", _stub_generate)
    main_module._pipeline = RAGPipeline(retriever=BM25Retriever())

    client = TestClient(main_module.app)
    response = client.post("/chat", json={"question": "What's the refund window for annual plans?"})

    assert response.status_code == 200
    body = response.json()
    assert body["answer"].startswith("stub answer for:")
    assert body["retrieved_contexts"]
