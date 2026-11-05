"""Retrieve-then-generate RAG pipeline. Retrieval is BM25 (no API cost); generation goes
to whichever provider `llm_config` names -- OpenAI or a self-hosted Ollama endpoint.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from app.llm import LLMConfig, generate_answer
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
    def __init__(
        self,
        retriever: BM25Retriever | None = None,
        top_k: int = TOP_K,
        llm_config: LLMConfig | None = None,
    ):
        self.retriever = retriever or BM25Retriever()
        self.top_k = top_k
        self.llm_config = llm_config

    def answer(self, question: str) -> PipelineResult:
        docs = self.retriever.retrieve(question, k=self.top_k)
        contexts = [d.text for d in docs]
        generation = generate_answer(question, contexts, config=self.llm_config)
        return PipelineResult(
            question=question,
            answer=generation.answer,
            retrieved_contexts=contexts,
            retrieved_doc_ids=[d.id for d in docs],
            input_tokens=generation.input_tokens,
            output_tokens=generation.output_tokens,
        )
