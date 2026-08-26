"""The CRAG relevance grader: score each retrieved chunk 0-1 against the query.

Two implementations of the same `Grader` protocol:

- `HeuristicGrader` -- deterministic query-term-overlap scoring. Free, instant,
  offline. This is the "keyword-overlap grader" concept.md compares against an
  LLM judge: it catches lexical relevance but misses paraphrase/semantic relevance
  ("revenue" vs "top-line income").
- `LLMGrader` -- an actual LLM-as-judge call via Instructor, returning a validated
  `RelevanceScore`. Needs ANTHROPIC_API_KEY. This is a plain hand-written prompt (the
  same shape as the reference CRAG notebook's `retrieval_evaluator`) -- see
  concept.md's note on DSPy-based prompt optimization being deferred for a future week.

Both are swappable behind the same interface so app/crag.py doesn't care which one
it's holding.
"""

from __future__ import annotations

import re
from statistics import mean
from typing import Protocol

import instructor
from pydantic import BaseModel, Field

from app.config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL

GRADER_SYSTEM_PROMPT = (
    "You are a strict retrieval-relevance grader for a RAG system. Given a user "
    "query and one retrieved chunk, score how relevant the chunk is to answering "
    "the query, from 0.0 (irrelevant) to 1.0 (directly and fully answers it). "
    "Partial relevance (on-topic but doesn't answer the question) should score "
    "around 0.3-0.6. Be strict: topical overlap alone is not high relevance."
)


class RelevanceScore(BaseModel):
    relevance: float = Field(ge=0.0, le=1.0, description="0.0 = irrelevant, 1.0 = fully relevant")
    reasoning: str = Field(description="one-sentence justification for the score")


class Grader(Protocol):
    def grade(self, query: str, chunk: str) -> RelevanceScore: ...


WORD_RE = re.compile(r"[a-z0-9]+")

# Excluded so two chunks don't look equally "relevant" just because they both
# contain "what"/"our"/"is" -- only content words should drive the overlap score.
# Reused by app/query_rewriter.py and app/refiner.py's heuristic implementations too.
STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "what", "why", "how", "when", "where", "who", "which", "does", "do", "did",
    "our", "your", "my", "their", "his", "her", "its", "this", "that", "these", "those",
    "for", "of", "in", "on", "at", "to", "and", "or", "but", "with", "about", "as",
    "it", "we", "you", "i", "he", "she", "they",
}


def content_terms(text: str) -> set[str]:
    """Lowercased content words (alnum tokens, stopwords excluded)."""
    return {t for t in WORD_RE.findall(text.lower()) if t not in STOPWORDS}


def _tokens(text: str) -> set[str]:
    return content_terms(text)


class HeuristicGrader:
    """Deterministic relevance = fraction of query content-terms present in the chunk."""

    def grade(self, query: str, chunk: str) -> RelevanceScore:
        query_terms = _tokens(query)
        chunk_terms = _tokens(chunk)
        if not query_terms:
            return RelevanceScore(relevance=0.0, reasoning="empty or all-stopword query")

        overlap = query_terms & chunk_terms
        relevance = len(overlap) / len(query_terms)

        if overlap:
            reasoning = f"{len(overlap)}/{len(query_terms)} query terms found in chunk: {sorted(overlap)}"
        else:
            reasoning = "no query terms found in chunk"

        return RelevanceScore(relevance=relevance, reasoning=reasoning)


class LLMGrader:
    """LLM-as-judge grader: Instructor + Anthropic, validated by `RelevanceScore`."""

    def __init__(self, model: str | None = None, max_tokens: int = 300):
        if not ANTHROPIC_API_KEY:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set -- LLMGrader needs a real API key. "
                "Use HeuristicGrader for offline grading, or set ANTHROPIC_API_KEY."
            )
        self._client = instructor.from_provider(
            f"anthropic/{model or ANTHROPIC_MODEL}", max_tokens=max_tokens
        )

    def grade(self, query: str, chunk: str) -> RelevanceScore:
        return self._client.create(
            response_model=RelevanceScore,
            messages=[
                {"role": "system", "content": GRADER_SYSTEM_PROMPT},
                {"role": "user", "content": f"Query: {query}\n\nChunk: {chunk}"},
            ],
        )


def grade_batch(grader: Grader, query: str, chunks: list[str]) -> list[RelevanceScore]:
    return [grader.grade(query, chunk) for chunk in chunks]


def mean_relevance(scores: list[RelevanceScore]) -> float:
    if not scores:
        return 0.0
    return mean(s.relevance for s in scores)
