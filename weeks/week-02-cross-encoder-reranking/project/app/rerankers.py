"""Stage 2 of the two-stage pipeline: cross-encoder reranking over Stage 1's
candidate pool (retriever.hybrid_candidates).

A bi-encoder (Stage 1) embeds the query and each document independently, so
it can only compare them with a cheap vector op -- that's what makes it fast
enough to search a whole corpus, and also why it's imprecise: the model
never actually looks at query and document together. A cross-encoder (Stage
2) takes the (query, document) pair as joint input and outputs one
relevance score per pair -- much more accurate, much more expensive, so it
only ever runs over the small pool Stage 1 already narrowed things down to.
See concept.md.

Every reranker in this module implements the same three-argument
`rerank(query, candidates, top_n) -> list[RerankResult]` shape so
benchmark.py can loop over them identically regardless of which one is
running underneath.
"""

import time
from dataclasses import dataclass
from typing import Protocol


@dataclass
class RerankResult:
    doc_id: int
    score: float


class Reranker(Protocol):
    name: str

    def rerank(
        self, query: str, candidates: list[tuple[int, str, str]], top_n: int
    ) -> list[RerankResult]: ...


class RerankerUnavailable(Exception):
    """Raised when a reranker can't run in this environment (e.g. no API
    key) -- benchmark.py catches this once per reranker, not per query, and
    reports the column as skipped rather than crashing the whole run."""


class NoOpReranker:
    """Baseline: Stage 1's hybrid order, truncated to top_n and left
    untouched. Not a real reranker -- it's the "no Stage 2" column the other
    two are measured against."""

    name = "no-rerank (hybrid only)"

    def rerank(
        self, query: str, candidates: list[tuple[int, str, str]], top_n: int
    ) -> list[RerankResult]:
        # candidates arrive already hybrid-ranked best-first; RRF score isn't
        # carried in the tuple here, so use rank order as a score surrogate.
        return [
            RerankResult(doc_id=doc_id, score=1.0 / (rank + 1))
            for rank, (doc_id, _title, _content) in enumerate(candidates[:top_n])
        ]


class CohereReranker:
    """Managed reranking via the Cohere Rerank API. Requires COHERE_API_KEY
    -- raises RerankerUnavailable at construction time if it's not set, so
    callers can decide once whether to include this column at all.

    Trial keys are capped at 10 calls/minute, and this benchmark makes one
    call per query (25 of them) back-to-back, so an unthrottled run starts
    hitting 429s partway through. Two layers guard against that: `rerank`
    paces itself to stay under COHERE_RATE_LIMIT_PER_MIN before each call
    (avoiding the 429 in the first place), and retries with backoff if a
    429 slips through anyway (e.g. another process sharing the same trial
    key, or clock drift)."""

    name = "cohere"

    # Number of times to retry a single rerank call after a 429 before
    # giving up and letting the error propagate.
    _MAX_RETRIES = 5

    def __init__(self, api_key: str | None = None, model: str | None = None):
        from app.config import COHERE_API_KEY, COHERE_RATE_LIMIT_PER_MIN, COHERE_RERANK_MODEL

        api_key = api_key or COHERE_API_KEY
        if not api_key:
            raise RerankerUnavailable(
                "COHERE_API_KEY is not set -- get a free trial key at "
                "https://dashboard.cohere.com/api-keys and put it in .env "
                "to include this reranker in the benchmark."
            )
        import cohere

        self._client = cohere.ClientV2(api_key=api_key)
        self._model = model or COHERE_RERANK_MODEL
        self._min_interval_s = (
            60.0 / COHERE_RATE_LIMIT_PER_MIN if COHERE_RATE_LIMIT_PER_MIN > 0 else 0.0
        )
        self._last_call_at: float | None = None

    def rerank(
        self, query: str, candidates: list[tuple[int, str, str]], top_n: int
    ) -> list[RerankResult]:
        from cohere.errors import TooManyRequestsError

        documents = [content for _doc_id, _title, content in candidates]

        for attempt in range(self._MAX_RETRIES + 1):
            self._throttle()
            try:
                response = self._client.rerank(
                    model=self._model,
                    query=query,
                    documents=documents,
                    top_n=top_n,
                )
                break
            except TooManyRequestsError:
                if attempt == self._MAX_RETRIES:
                    raise
                # Exponential backoff (5s, 10s, 20s, ...) -- the trial
                # limit resets on a rolling window, so a short wait is
                # usually enough to free up quota again.
                time.sleep(5 * (2**attempt))

        return [
            RerankResult(
                doc_id=candidates[result.index][0],
                score=result.relevance_score,
            )
            for result in response.results
        ]

    def _throttle(self) -> None:
        """Block just long enough to keep calls at or below
        COHERE_RATE_LIMIT_PER_MIN, so a full benchmark run paces itself
        under the trial quota instead of bursting through it."""
        if self._min_interval_s <= 0 or self._last_call_at is None:
            self._last_call_at = time.monotonic()
            return
        elapsed = time.monotonic() - self._last_call_at
        remaining = self._min_interval_s - elapsed
        if remaining > 0:
            time.sleep(remaining)
        self._last_call_at = time.monotonic()


class BGEReranker:
    """Self-hosted reranking via a local BGE cross-encoder
    (sentence-transformers). No API key, no network call per query -- the
    model downloads once (~1.1GB) on first construction and is cached under
    ~/.cache/huggingface, then runs on CPU."""

    name = "bge-reranker-base"

    def __init__(self, model_name: str | None = None):
        from sentence_transformers import CrossEncoder

        from app.config import BGE_RERANKER_MODEL

        self._model = CrossEncoder(model_name or BGE_RERANKER_MODEL)

    def rerank(
        self, query: str, candidates: list[tuple[int, str, str]], top_n: int
    ) -> list[RerankResult]:
        pairs = [[query, content] for _doc_id, _title, content in candidates]
        scores = self._model.predict(pairs)
        ranked = sorted(
            zip(candidates, scores), key=lambda pair: pair[1], reverse=True
        )[:top_n]
        return [
            RerankResult(doc_id=doc_id, score=float(score))
            for (doc_id, _title, _content), score in ranked
        ]
