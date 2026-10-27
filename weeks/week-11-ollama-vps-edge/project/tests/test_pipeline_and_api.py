from fastapi.testclient import TestClient

import app.main as main_module
from app.llm import LLMConfig
from app.pipeline import RAGPipeline
from app.retrieval import BM25Retriever


def test_pipeline_retrieves_right_doc_and_passes_config(pipeline, stub_generate):
    result = pipeline.answer("How many days do I have to request a refund on an annual plan?")
    assert "refunds" in result.retrieved_doc_ids
    assert result.answer.startswith("stub answer for:")
    assert (result.input_tokens, result.output_tokens) == (42, 7)
    assert stub_generate[0].provider == "ollama"


def test_health_reports_provider(monkeypatch, stub_generate):
    cfg = LLMConfig(provider="ollama", model="llama3.2:3b", base_url="http://x")
    monkeypatch.setattr(main_module, "_pipeline", RAGPipeline(retriever=BM25Retriever(), llm_config=cfg))
    body = TestClient(main_module.app).get("/health").json()
    assert body == {"status": "ok", "provider": "ollama", "model": "llama3.2:3b"}


def test_chat_returns_answer_provider_and_contexts(monkeypatch, stub_generate):
    cfg = LLMConfig(provider="ollama", model="llama3.2:3b", base_url="http://x")
    monkeypatch.setattr(main_module, "_pipeline", RAGPipeline(retriever=BM25Retriever(), llm_config=cfg))
    response = TestClient(main_module.app).post("/chat", json={"question": "What's the Pro rate limit?"})
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "ollama" and body["model"] == "llama3.2:3b"
    assert "rate-limits" in body["retrieved_doc_ids"]
    assert body["retrieved_contexts"]


def test_chat_rejects_missing_question(monkeypatch, stub_generate):
    assert TestClient(main_module.app).post("/chat", json={}).status_code == 422
