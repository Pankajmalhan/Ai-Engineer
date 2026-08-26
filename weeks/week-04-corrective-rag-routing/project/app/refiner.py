"""Knowledge refinement: strip selected context down to its most relevant key points.

This is CRAG's "decompose-then-recompose" step: rather than handing the generator
whole chunks (which may be mostly irrelevant sentences around one useful one), break
each piece of context into sentences/facts, keep only the ones that actually bear on
the query, and recompose those into a short bullet list.
"""

from __future__ import annotations

import re
from typing import Protocol

import instructor
from pydantic import BaseModel, Field

from app.config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL
from app.grader import content_terms

REFINER_SYSTEM_PROMPT = (
    "Given a user query and one or more retrieved passages, extract only the "
    "sentences or facts that are directly relevant to answering the query. Discard "
    "anything off-topic. Return each as a short, self-contained bullet point."
)


class KeyPoints(BaseModel):
    bullets: list[str] = Field(description="relevant facts extracted from the context", max_length=5)


class Refiner(Protocol):
    def refine(self, query: str, texts: list[str]) -> list[str]: ...


_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n+")


class HeuristicRefiner:
    """Splits texts into sentences, scores each by query-term overlap, keeps the top few."""

    def __init__(self, max_bullets: int = 3):
        self.max_bullets = max_bullets

    def refine(self, query: str, texts: list[str]) -> list[str]:
        query_terms = content_terms(query)

        sentences = [
            sent.strip()
            for text in texts
            for sent in _SENTENCE_RE.split(text.strip())
            if sent.strip()
        ]
        if not sentences:
            return []

        scored = [(sent, len(query_terms & content_terms(sent))) for sent in sentences]
        scored.sort(key=lambda pair: pair[1], reverse=True)

        # "decompose-then-recompose": discard the zero-overlap sentences rather than
        # padding out to max_bullets with them once the relevant ones run out. Only
        # fall back to the (all zero-scoring) top-N if literally nothing overlapped,
        # so refine() never silently returns an empty list when it has *some* text.
        relevant = [sent for sent, score in scored if score > 0]
        if relevant:
            return relevant[: self.max_bullets]
        return [sent for sent, _score in scored[: self.max_bullets]]


class LLMRefiner:
    def __init__(self, model: str | None = None, max_tokens: int = 400):
        if not ANTHROPIC_API_KEY:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set -- LLMRefiner needs a real API key. "
                "Use HeuristicRefiner for offline refinement, or set ANTHROPIC_API_KEY."
            )
        self._client = instructor.from_provider(
            f"anthropic/{model or ANTHROPIC_MODEL}", max_tokens=max_tokens
        )

    def refine(self, query: str, texts: list[str]) -> list[str]:
        if not texts:
            return []
        passages = "\n\n".join(f"Passage {i + 1}: {t}" for i, t in enumerate(texts))
        result = self._client.create(
            response_model=KeyPoints,
            messages=[
                {"role": "system", "content": REFINER_SYSTEM_PROMPT},
                {"role": "user", "content": f"Query: {query}\n\n{passages}"},
            ],
        )
        return result.bullets
