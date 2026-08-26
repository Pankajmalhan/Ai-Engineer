"""Corrective RAG: retrieve -> grade -> {Correct, Incorrect, Ambiguous} -> act -> generate.

This now follows the CRAG paper's actual design (see concept.md's "Corrective RAG
(CRAG)" section) rather than the single-mean-threshold simplification this project
started with:

    max(chunk scores) > UPPER   -> Correct:    refine retrieval, skip web search
    max(chunk scores) < LOWER   -> Incorrect:  discard retrieval, rewrite query, web search
    LOWER <= max <= UPPER       -> Ambiguous:  refine retrieval AND web search, combine

Every branch's context is passed through the knowledge refiner (decompose-then-
recompose to key bullet points) before the final answer is generated.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from statistics import mean
from typing import Callable

from app.answerer import Answerer
from app.config import RELEVANCE_LOWER_THRESHOLD, RELEVANCE_UPPER_THRESHOLD
from app.grader import Grader, RelevanceScore, grade_batch
from app.models import RetrievedChunk
from app.query_rewriter import QueryRewriter
from app.refiner import Refiner
from app.web_search import WebSearch, WebSearchResult

RetrieveFn = Callable[[str], list[RetrievedChunk]]


class CragAction(str, Enum):
    CORRECT = "correct"
    INCORRECT = "incorrect"
    AMBIGUOUS = "ambiguous"


@dataclass
class CragResult:
    action: CragAction
    max_relevance: float
    mean_relevance: float
    chunk_scores: list[RelevanceScore]
    context: list[str]        # refined bullet points, whatever their source
    answer: str
    rewritten_query: str | None = None
    web_results: list[WebSearchResult] | None = None


class CorrectiveRAG:
    def __init__(
        self,
        retrieve_fn: RetrieveFn,
        grader: Grader,
        refiner: Refiner,
        rewriter: QueryRewriter,
        web_search: WebSearch,
        answerer: Answerer,
        upper_threshold: float = RELEVANCE_UPPER_THRESHOLD,
        lower_threshold: float = RELEVANCE_LOWER_THRESHOLD,
    ):
        self.retrieve_fn = retrieve_fn
        self.grader = grader
        self.refiner = refiner
        self.rewriter = rewriter
        self.web_search = web_search
        self.answerer = answerer
        self.upper_threshold = upper_threshold
        self.lower_threshold = lower_threshold

    def run(self, query: str) -> CragResult:
        chunks = self.retrieve_fn(query)
        scores = grade_batch(self.grader, query, [c.text for c in chunks]) if chunks else []
        max_rel = max((s.relevance for s in scores), default=0.0)
        mean_rel = mean((s.relevance for s in scores)) if scores else 0.0

        rewritten_query: str | None = None
        web_results: list[WebSearchResult] | None = None

        if max_rel > self.upper_threshold:
            action = CragAction.CORRECT
            raw_context = [c.text for c in chunks]

        elif max_rel < self.lower_threshold:
            action = CragAction.INCORRECT
            rewritten_query = self.rewriter.rewrite(query)
            web_results = self.web_search.search(rewritten_query)
            raw_context = [r.content for r in web_results]

        else:
            action = CragAction.AMBIGUOUS
            rewritten_query = self.rewriter.rewrite(query)
            web_results = self.web_search.search(rewritten_query)
            raw_context = [c.text for c in chunks] + [r.content for r in web_results]

        refined_context = self.refiner.refine(query, raw_context)
        answer = self.answerer.answer(query, refined_context)

        return CragResult(
            action=action,
            max_relevance=max_rel,
            mean_relevance=mean_rel,
            chunk_scores=scores,
            context=refined_context,
            answer=answer,
            rewritten_query=rewritten_query,
            web_results=web_results,
        )
