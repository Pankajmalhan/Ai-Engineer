"""Rewrite a user query into something better suited to a web search engine, before
CRAG's Incorrect/Ambiguous branches hand it to app/web_search.py.

A natural-language question ("Why does getUserById() throw a NullPointerException?")
is not what you'd type into a search engine -- a search engine wants the keywords
("getUserById NullPointerException cause"). The CRAG paper does this with an LLM;
`HeuristicRewriter` approximates it offline by stripping stopwords/question phrasing.
"""

from __future__ import annotations

import re
from typing import Protocol

import instructor
from pydantic import BaseModel, Field

from app.config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL
from app.grader import STOPWORDS

REWRITER_SYSTEM_PROMPT = (
    "Rewrite the user's question into a short, keyword-focused query optimized for a "
    "web search engine. Keep identifiers, error messages, and technical terms intact. "
    "Drop question words and filler. Return only the rewritten query."
)


class RewrittenQuery(BaseModel):
    query: str = Field(description="the search-engine-optimized rewrite")


class QueryRewriter(Protocol):
    def rewrite(self, query: str) -> str: ...


_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


class HeuristicRewriter:
    """Drops stopwords/question phrasing, keeps original casing (identifiers, acronyms)."""

    def rewrite(self, query: str) -> str:
        tokens = _TOKEN_RE.findall(query)
        content_tokens = [t for t in tokens if t.lower() not in STOPWORDS]
        return " ".join(content_tokens) if content_tokens else query


class LLMRewriter:
    def __init__(self, model: str | None = None, max_tokens: int = 100):
        if not ANTHROPIC_API_KEY:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set -- LLMRewriter needs a real API key. "
                "Use HeuristicRewriter for offline rewriting, or set ANTHROPIC_API_KEY."
            )
        self._client = instructor.from_provider(
            f"anthropic/{model or ANTHROPIC_MODEL}", max_tokens=max_tokens
        )

    def rewrite(self, query: str) -> str:
        result = self._client.create(
            response_model=RewrittenQuery,
            messages=[
                {"role": "system", "content": REWRITER_SYSTEM_PROMPT},
                {"role": "user", "content": query},
            ],
        )
        return result.query
