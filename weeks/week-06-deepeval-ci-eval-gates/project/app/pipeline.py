"""The retrieve-then-generate RAG pipeline this week evaluates. Retrieval is BM25 (no
API cost); generation calls OpenAI and needs OPENAI_API_KEY (app/llm.py).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import RETRIEVAL_TOP_K
from app.llm import generate_answer
from app.retrieval import BM25Retriever


@dataclass
class PipelineResult:
    user_input: str
    response: str
    retrieved_contexts: list[str]


class RAGPipeline:
    def __init__(self, retriever: BM25Retriever | None = None, top_k: int = RETRIEVAL_TOP_K):
        self.retriever = retriever or BM25Retriever()
        self.top_k = top_k

    def answer(self, question: str) -> PipelineResult:
        contexts = self.retriever.retrieve(question, k=self.top_k)
        response = generate_answer(question, contexts)
        return PipelineResult(user_input=question, response=response, retrieved_contexts=contexts)
