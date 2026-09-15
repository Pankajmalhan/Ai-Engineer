"""Thin OpenAI wrapper for the pipeline's generation step. Gated behind OPENAI_API_KEY
the same way prior weeks gate optional real-model paths (Presidio/spaCy in week 1c) --
openai_available() lets callers/tests skip cleanly instead of crashing when no key is
configured.
"""

from __future__ import annotations

from functools import lru_cache

from app.config import OPENAI_API_KEY, OPENAI_MODEL

SYSTEM_PROMPT = (
    "Answer the question using only the provided context. If the context doesn't "
    "contain the answer, say you don't know. Be concise -- one or two sentences."
)


def openai_available() -> bool:
    return bool(OPENAI_API_KEY)


@lru_cache(maxsize=1)
def _client():
    from openai import OpenAI

    return OpenAI(api_key=OPENAI_API_KEY)


def generate_answer(question: str, contexts: list[str]) -> str:
    context_block = "\n\n".join(contexts)
    response = _client().chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Context:\n{context_block}\n\nQuestion: {question}"},
        ],
        temperature=0,
    )
    return response.choices[0].message.content.strip()
