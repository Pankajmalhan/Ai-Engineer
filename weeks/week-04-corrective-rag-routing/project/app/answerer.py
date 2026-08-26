"""The final generation step: turn refined context into an answer.

CRAG's last stage after retrieve/grade/act/refine is still "generate a response" --
this project stopped short of that in its first pass. `ExtractiveAnswerer` is an
honest offline stand-in (it does not generate anything; it formats the bullets), and
`LLMAnswerer` is the real thing.
"""

from __future__ import annotations

from typing import Protocol

from app.config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL

ANSWERER_SYSTEM_PROMPT = (
    "Answer the user's question using ONLY the provided context. If the context "
    "doesn't contain the answer, say so plainly instead of guessing. Be concise."
)


class Answerer(Protocol):
    def answer(self, query: str, context: list[str]) -> str: ...


class ExtractiveAnswerer:
    """No generation -- just formats the refined bullets. Labeled as such in output
    so it's never mistaken for a real generated answer."""

    def answer(self, query: str, context: list[str]) -> str:
        if not context:
            return "[extractive, no LLM configured] No relevant context was found for this query."
        bullets = "\n".join(f"- {c}" for c in context)
        return f"[extractive, no LLM configured] Based on the retrieved context:\n{bullets}"


class LLMAnswerer:
    def __init__(self, model: str | None = None, max_tokens: int = 500):
        if not ANTHROPIC_API_KEY:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set -- LLMAnswerer needs a real API key. "
                "Use ExtractiveAnswerer for offline runs, or set ANTHROPIC_API_KEY."
            )
        import anthropic

        self._client = anthropic.Anthropic()
        self._model = model or ANTHROPIC_MODEL
        self._max_tokens = max_tokens

    def answer(self, query: str, context: list[str]) -> str:
        if not context:
            return "I don't have enough information to answer that."
        bullets = "\n".join(f"- {c}" for c in context)
        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=ANSWERER_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": f"Context:\n{bullets}\n\nQuestion: {query}"}],
        )
        return "".join(block.text for block in response.content if block.type == "text")
