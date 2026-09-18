"""The retrieve-then-generate RAG pipeline this week red-teams. Retrieval is BM25 (no
API cost); generation calls OpenAI and needs OPENAI_API_KEY.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from app.llm import generate_answer
from app.retrieval import BM25Retriever

TOP_K = int(os.environ.get("RETRIEVAL_TOP_K", "3"))


@dataclass
class PipelineResult:
    question: str
    answer: str
    retrieved_contexts: list[str]


class RAGPipeline:
    def __init__(self, retriever: BM25Retriever | None = None, top_k: int = TOP_K):
        self.retriever = retriever or BM25Retriever()
        self.top_k = top_k

    def answer(self, question: str) -> PipelineResult:
        contexts = self.retriever.retrieve(question, k=self.top_k)
        response = generate_answer(question, contexts)
        return PipelineResult(question=question, answer=response, retrieved_contexts=contexts)
