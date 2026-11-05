"""Scoring for one pipeline result against its answer key."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.queries import Query
from app.types import PipelineResult

_ABSTAIN = re.compile(
    r"don'?t know|do not know|doesn'?t (?:say|mention|specify|cover|contain)|not (?:mentioned|covered|specified|stated|provided|available|in the (?:docs|documentation))|"
    r"no (?:information|mention)|cannot (?:find|answer)|can'?t (?:find|answer)|couldn'?t find|unable to (?:find|answer)",
    re.IGNORECASE,
)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("**", "").replace("‑", "-")).lower()


def has_fact(answer: str, alternatives: tuple[str, ...]) -> bool:
    haystack = _norm(answer)
    return any(_norm(alt) in haystack for alt in alternatives)


def abstained(answer: str) -> bool:
    return bool(_ABSTAIN.search(answer))


@dataclass(frozen=True)
class Score:
    fact_recall: float  # share of required facts present (answerable queries; 0 for unanswerable)
    correct: bool  # answerable: ALL facts present and not abstaining; unanswerable: abstained
    abstained: bool
    retrieval_recall: float | None  # share of expected docs the Retriever returned
    kept_recall: float | None  # share of expected docs that survived the Grader
    kept_precision: float | None  # share of kept docs that were expected
    error: bool


def score(result: PipelineResult, query: Query) -> Score:
    if result.error:
        return Score(0.0, False, False, None, None, None, True)
    did_abstain = abstained(result.answer)
    if not query.answerable:
        return Score(0.0, did_abstain, did_abstain, None, None, None, False)
    recall = sum(has_fact(result.answer, alts) for alts in query.facts) / len(query.facts)
    expected = set(query.expected_docs)
    kept = set(result.kept_ids)
    return Score(
        fact_recall=recall,
        correct=recall == 1.0 and not did_abstain,
        abstained=did_abstain,
        retrieval_recall=len(expected & set(result.retrieved_ids)) / len(expected),
        kept_recall=len(expected & kept) / len(expected),
        kept_precision=(len(expected & kept) / len(kept)) if kept else 0.0,
        error=False,
    )
