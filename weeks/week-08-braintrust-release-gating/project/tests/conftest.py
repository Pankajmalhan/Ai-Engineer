from __future__ import annotations

import pytest

from app.llm import GenerationResult
from app.pipeline import RAGPipeline
from app.retrieval import BM25Retriever


@pytest.fixture
def pipeline(monkeypatch) -> RAGPipeline:
    """A pipeline whose generation step is stubbed -- no OPENAI_API_KEY, no network.
    Retrieval is real BM25 over the real fixture corpus.
    """

    def _fake_generate(question: str, contexts: list[str]) -> GenerationResult:
        return GenerationResult(answer=f"stub answer for: {question}", input_tokens=42, output_tokens=7)

    monkeypatch.setattr("app.pipeline.generate_answer", _fake_generate)
    return RAGPipeline(retriever=BM25Retriever())
