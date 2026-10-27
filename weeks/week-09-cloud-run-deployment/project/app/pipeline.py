"""The retrieve-then-generate RAG pipeline this week instruments and gates. Retrieval
is BM25 (no API cost); generation calls OpenAI and needs OPENAI_API_KEY.
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
    retrieved_doc_ids: list[str]
    input_tokens: int
    output_tokens: int


class RAGPipeline:
    def __init__(self, retriever: BM25Retriever | None = None, top_k: int = TOP_K):
        self.retriever = retriever or BM25Retriever()
        self.top_k = top_k

    def answer(self, question: str) -> PipelineResult:
        docs = self.retriever.retrieve(question, k=self.top_k)
        contexts = [d.text for d in docs]
        generation = generate_answer(question, contexts)
        return PipelineResult(
            question=question,
            answer=generation.answer,
            retrieved_contexts=contexts,
            retrieved_doc_ids=[d.id for d in docs],
            input_tokens=generation.input_tokens,
            output_tokens=generation.output_tokens,
        )
