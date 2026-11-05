from __future__ import annotations

import pytest

from app.llm import GenerationResult, LLMConfig
from app.pipeline import RAGPipeline
from app.retrieval import BM25Retriever


@pytest.fixture
def stub_generate(monkeypatch):
    """Replaces the generation step: no network, no keys. Retrieval stays real BM25."""
    calls = []

    def _fake(question, contexts, config=None, client=None):
        calls.append(config)
        return GenerationResult(answer=f"stub answer for: {question}", input_tokens=42, output_tokens=7)

    monkeypatch.setattr("app.pipeline.generate_answer", _fake)
    return calls


@pytest.fixture
def pipeline(stub_generate) -> RAGPipeline:
    return RAGPipeline(
        retriever=BM25Retriever(),
        llm_config=LLMConfig(provider="ollama", model="llama3.2:3b", base_url="http://x"),
    )
