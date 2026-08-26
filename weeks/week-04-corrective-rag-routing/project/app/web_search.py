"""The web search fallback CRAG escalates to when retrieval grades as low-relevance.

`TavilySearch` is the real thing. `LocalFallbackSearch` is an explicitly-labeled
offline substitute -- a tiny static snapshot -- used when no TAVILY_API_KEY is set, so
the CRAG pipeline (app/crag.py) and its tests can run the whole retrieve-grade-escalate
loop without a network call or a paid API key. It is not a claim that this is real web
search; see its docstring.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.config import TAVILY_API_KEY


@dataclass
class WebSearchResult:
    title: str
    url: str
    content: str


class WebSearch(Protocol):
    def search(self, query: str, max_results: int = 3) -> list[WebSearchResult]: ...


class TavilySearch:
    """Real web search via the Tavily API."""

    def __init__(self, api_key: str | None = None):
        api_key = api_key or TAVILY_API_KEY
        if not api_key:
            raise RuntimeError(
                "TAVILY_API_KEY is not set -- TavilySearch needs a real API key. "
                "Use LocalFallbackSearch for offline runs, or set TAVILY_API_KEY."
            )
        from tavily import TavilyClient  # imported lazily so the package is optional at runtime

        self._client = TavilyClient(api_key=api_key)

    def search(self, query: str, max_results: int = 3) -> list[WebSearchResult]:
        response = self._client.search(query, search_depth="basic", max_results=max_results)
        return [
            WebSearchResult(title=r.get("title", ""), url=r.get("url", ""), content=r.get("content", ""))
            for r in response.get("results", [])
        ]


# A tiny static "index" standing in for the open web, keyed by topic so
# LocalFallbackSearch can return something plausible for this project's demo
# queries without ever making a network call.
_OFFLINE_SNAPSHOT: list[WebSearchResult] = [
    WebSearchResult(
        title="ColBERT: Efficient and Effective Passage Search via Late Interaction",
        url="https://arxiv.org/abs/2004.12832",
        content=(
            "ColBERT introduces late interaction: independently encoding queries and "
            "documents into token-level vectors, then computing a cheap yet expressive "
            "MaxSim interaction between them at search time."
        ),
    ),
    WebSearchResult(
        title="Corrective Retrieval Augmented Generation",
        url="https://arxiv.org/abs/2401.15884",
        content=(
            "CRAG designs a lightweight retrieval evaluator to assess the overall "
            "quality of retrieved documents, triggering different knowledge retrieval "
            "actions -- Correct, Incorrect, Ambiguous -- including a web search fallback."
        ),
    ),
    WebSearchResult(
        title="DSPy: Compiling Declarative Language Model Calls",
        url="https://arxiv.org/abs/2310.03714",
        content=(
            "DSPy replaces hand-written prompt strings with declarative signatures and "
            "modules, then uses optimizers (teleprompters) to compile them into "
            "effective prompts and few-shot demonstrations against a metric."
        ),
    ),
    WebSearchResult(
        title="Reciprocal Rank Fusion outperforms Condorcet and individual rank learning methods",
        url="https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf",
        content=(
            "Reciprocal rank fusion combines multiple ranked lists into one by summing "
            "1/(k + rank) across lists, a simple and robust way to fuse sparse (BM25) "
            "and dense retrieval rankings without training a combiner."
        ),
    ),
]


class LocalFallbackSearch:
    """Offline stand-in for web search: term-overlap lookup over a static snapshot.

    Used when TAVILY_API_KEY isn't set, and in tests, so CRAG's fallback path is fully
    exercised without a network call. Swap for TavilySearch to hit the real web.
    """

    def __init__(self, snapshot: list[WebSearchResult] | None = None):
        self._snapshot = snapshot if snapshot is not None else _OFFLINE_SNAPSHOT

    def search(self, query: str, max_results: int = 3) -> list[WebSearchResult]:
        query_terms = set(query.lower().split())

        def overlap(result: WebSearchResult) -> int:
            text = f"{result.title} {result.content}".lower()
            return sum(1 for term in query_terms if term in text)

        ranked = sorted(self._snapshot, key=overlap, reverse=True)
        return ranked[:max_results]
