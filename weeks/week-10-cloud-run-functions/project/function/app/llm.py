"""Thin OpenAI wrapper for the pipeline's generation step.

Deliberately lighter than Week 9's app/llm.py: no `braintrust.wrap_openai`, no
Langfuse/Ragas anywhere in this dependency tree. That's the whole point of this
week's "lightweight" RAG endpoint -- every dependency here is one more thing Cloud
Run has to import before a cold container can serve its first request (see
concept.md's cold-start section for the actual measured effect of this).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

SYSTEM_PROMPT = (
    "You are the Northwind API support assistant. Answer the customer's question using "
    "only the provided context. If the context doesn't contain the answer, say you "
    "don't know. Be concise -- one or two sentences."
)


@dataclass
class GenerationResult:
    answer: str
    input_tokens: int
    output_tokens: int


def openai_available() -> bool:
    return bool(OPENAI_API_KEY)


@lru_cache(maxsize=1)
def _client():
    from openai import OpenAI

    return OpenAI(api_key=OPENAI_API_KEY)


def generate_answer(question: str, contexts: list[str]) -> GenerationResult:
    context_block = "\n\n".join(contexts)
    response = _client().chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Context:\n{context_block}\n\nQuestion: {question}"},
        ],
        temperature=0,
    )
    return GenerationResult(
        answer=response.choices[0].message.content.strip(),
        input_tokens=response.usage.prompt_tokens,
        output_tokens=response.usage.completion_tokens,
    )
