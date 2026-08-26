"""Query router: classify a query, dispatch to the retrieval strategy that fits it.

See concept.md's "Query routing" section for the reasoning. `SemanticRouter` is a
semantic router (TF-IDF-similarity-to-labeled-prototype-queries, the offline/no-API-key
cousin of embedding-similarity routing) with a small heuristic booster for the CODE
class, since surface features (code fences, identifier casing, stack-trace language)
separate code questions from prose better than bag-of-words similarity alone.

`CascadingRouter` wraps it with a second tier: when `SemanticRouter` isn't confident
enough to commit, escalate to an LLM classifier (`LLMRouteClassifier`) instead of
silently defaulting -- and log every escalation, so the low-confidence queries that
required an LLM call become raw material for growing `PROTOTYPES` and shrinking the
escalation rate over time. See this file's `CascadingRouter` docstring for the design.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Protocol

import instructor
from pydantic import BaseModel, Field
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL, ROUTER_MIN_CONFIDENCE


class Strategy(str, Enum):
    FACTUAL = "factual"
    CODE = "code"
    CONVERSATIONAL = "conversational"


# What each route actually dispatches to downstream (app/pipeline.py reads this).
# FACTUAL and CODE both resolve to the same hybrid_search function -- BM25+pgvector,
# fused by RRF -- over different pgvector collections with different fusion weights
# (CODE weights BM25 more heavily: exact identifiers/error strings matter more there
# than semantic similarity). See concept.md for why this replaces a separate
# ColBERT-backed CODE route.
STRATEGY_TO_RETRIEVAL = {
    Strategy.FACTUAL: "hybrid_search[docs]",
    Strategy.CODE: "hybrid_search[code, bm25-weighted]",
    Strategy.CONVERSATIONAL: "direct_llm",
}

# The safe default for queries the router isn't confident about: general-purpose
# retrieval beats guessing between "no retrieval" and "specialized retrieval".
DEFAULT_STRATEGY = Strategy.FACTUAL

# Labeled seed set of example queries per class. Grown from an initial 8/class to
# ~25/class specifically to reduce how often SemanticRouter has to fall back on
# CascadingRouter's LLM escalation -- in a real production router this would keep
# growing from CascadingRouter's own escalation log (see that class below), not stay
# hand-written forever.
PROTOTYPES: dict[Strategy, list[str]] = {
    Strategy.FACTUAL: [
        "What is our refund policy for annual plans?",
        "How many employees does the company have?",
        "What year was the company founded?",
        "What is the capital of France?",
        "Summarize the Q3 earnings report",
        "What's included in the enterprise pricing tier?",
        "When is the next public holiday?",
        "What does the SLA guarantee for uptime?",
        "Can I get my money back if I cancel early?",
        "How much does the pro plan cost per month?",
        "Where is the company headquartered?",
        "What's the difference between the free and paid tiers?",
        "Do you offer discounts for students?",
        "What time zone is support available in?",
        "How do I cancel my subscription?",
        "What's the maximum file size I can upload?",
        "Is there a mobile app available?",
        "What payment methods do you accept?",
        "How long does shipping usually take?",
        "What's your data retention policy?",
        "Who is the CEO of the company?",
        "What's 15% of 200?",
        "How many days are in a leap year?",
        "What's the population of Japan?",
        "Does the warranty cover accidental damage?",
    ],
    Strategy.CODE: [
        "Why does getUserById() throw a NullPointerException?",
        "Fix this Python traceback: IndexError: list index out of range",
        "How do I resolve a merge conflict in git?",
        "What does this stack trace mean: Exception in thread main",
        "Write a function to reverse a linked list",
        "Debug this TypeError: cannot read property of undefined",
        "How do I configure retries in the requests library?",
        "Explain this regex: ^[a-z0-9_]+$",
        "Why is my React component re-rendering infinitely?",
        "How do I fix a segmentation fault in C?",
        "What's causing this KeyError in my dictionary lookup?",
        "How do I make an async function in JavaScript?",
        "Why does this SQL query return duplicate rows?",
        "Explain what a race condition is in multithreaded code",
        "How do I mock a database call in pytest?",
        "What does 'undefined is not a function' mean?",
        "How do I set up a virtual environment in Python?",
        "Why is docker build failing with 'no space left on device'?",
        "How do I fix a 500 Internal Server Error in Flask?",
        "What's the difference between == and === in JavaScript?",
        "How do I write a unit test for this function?",
        "Why is my API returning a 401 Unauthorized error?",
        "How do I optimize this O(n^2) algorithm?",
        "Explain the difference between a list and a tuple in Python",
        "How do I revert the last git commit without losing changes?",
    ],
    Strategy.CONVERSATIONAL: [
        "Hi, how are you?",
        "Thanks, that's helpful!",
        "Good morning",
        "Can you tell me a joke?",
        "What's your name?",
        "That makes sense, appreciate it",
        "See you later",
        "Nice chatting with you",
        "Hey there",
        "How's it going?",
        "You're awesome, thanks",
        "lol that's funny",
        "Okay cool, thanks for the help",
        "Goodnight",
        "What's up?",
        "Nice to meet you",
        "Have a great day",
        "Sounds good, thanks!",
        "Can we chat for a bit?",
        "You're really helpful",
        "Just saying hi",
        "Cool, got it",
        "Appreciate your time",
        "Talk soon",
        "That's awesome, thank you",
    ],
}

# Structural signals that a query is about code, independent of its wording.
_CODE_PATTERNS = [
    re.compile(r"```"),                          # code fence
    re.compile(r"`[^`]+`"),                       # inline code
    re.compile(r"\b\w+\([^)]*\)"),                # function call syntax
    re.compile(r"\b(traceback|exception|stack ?trace|nullpointer|typeerror|"
               r"indexerror|syntax ?error|undefined is not|null pointer)\b", re.I),
    re.compile(r"\.\w{1,4}\b(?=[\s:,.]|$)"),      # file-extension-ish token, e.g. .py .js
    re.compile(r"\b[a-z]+_[a-z_]+\b"),            # snake_case identifier
    re.compile(r"\b[a-z]+[A-Z][a-zA-Z]*\b"),      # camelCase identifier
]


def _code_heuristic_score(query: str) -> float:
    hits = sum(1 for pattern in _CODE_PATTERNS if pattern.search(query))
    return min(1.0, 0.2 * hits)


@dataclass
class RouteDecision:
    strategy: Strategy
    confidence: float
    scores: dict[Strategy, float]
    used_default_fallback: bool = False
    # True only when CascadingRouter escalated this decision to an LLM call --
    # `used_default_fallback` still reflects that Tier 1 (SemanticRouter) itself
    # wasn't confident; this records that Tier 2 then made the actual call.
    escalated_to_llm: bool = False

    @property
    def retrieval_strategy(self) -> str:
        return STRATEGY_TO_RETRIEVAL[self.strategy]


class Router(Protocol):
    """What both SemanticRouter and CascadingRouter implement -- app/pipeline.py
    only depends on this, not on which tier(s) actually produced the decision."""

    def route(self, query: str) -> RouteDecision: ...


class SemanticRouter:
    """Routes a query to a Strategy using TF-IDF similarity to labeled prototypes."""

    def __init__(self, prototypes: dict[Strategy, list[str]] | None = None,
                 min_confidence: float = ROUTER_MIN_CONFIDENCE):
        self.prototypes = prototypes or PROTOTYPES
        self.min_confidence = min_confidence

        all_examples: list[str] = []
        self._example_classes: list[Strategy] = []
        for strategy, examples in self.prototypes.items():
            all_examples.extend(examples)
            self._example_classes.extend([strategy] * len(examples))

        self._vectorizer = TfidfVectorizer()
        self._example_matrix = self._vectorizer.fit_transform(all_examples)

    def _semantic_scores(self, query: str) -> dict[Strategy, float]:
        query_vec = self._vectorizer.transform([query])
        sims = cosine_similarity(query_vec, self._example_matrix)[0]

        scores: dict[Strategy, float] = {s: 0.0 for s in self.prototypes}
        for sim, strategy in zip(sims, self._example_classes):
            if sim > scores[strategy]:
                scores[strategy] = float(sim)
        return scores

    def route(self, query: str) -> RouteDecision:
        scores = self._semantic_scores(query)
        scores[Strategy.CODE] = min(1.0, scores[Strategy.CODE] + _code_heuristic_score(query))

        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        top_strategy, top_score = ranked[0]
        second_score = ranked[1][1] if len(ranked) > 1 else 0.0
        confidence = top_score - second_score

        if confidence < self.min_confidence:
            return RouteDecision(
                strategy=DEFAULT_STRATEGY,
                confidence=confidence,
                scores=scores,
                used_default_fallback=True,
            )

        return RouteDecision(strategy=top_strategy, confidence=confidence, scores=scores)


ROUTER_SYSTEM_PROMPT = (
    "Classify the user's query into exactly one category:\n"
    "- factual: a question seeking information -- company policy, pricing, general "
    "knowledge, dates, numbers, anything answerable from a document or fact.\n"
    "- code: a question about code, a programming error, debugging, or software "
    "development -- even if it's short or doesn't look like a full sentence.\n"
    "- conversational: greetings, thanks, small talk, or chit-chat that needs no "
    "retrieval at all.\n"
    "Respond with the single best-fitting category and a one-sentence reason."
)


class RouterClassification(BaseModel):
    strategy: Strategy
    reasoning: str = Field(description="one-sentence justification for the category")


class LLMRouteClassifier:
    """Tier 2 of CascadingRouter: an actual LLM call, only made for the queries
    SemanticRouter itself couldn't confidently classify."""

    def __init__(self, model: str | None = None, max_tokens: int = 150):
        if not ANTHROPIC_API_KEY:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set -- LLMRouteClassifier needs a real API "
                "key. Leave CascadingRouter's llm_classifier unset to use "
                "SemanticRouter's own default-strategy fallback instead, or set "
                "ANTHROPIC_API_KEY."
            )
        self._client = instructor.from_provider(
            f"anthropic/{model or ANTHROPIC_MODEL}", max_tokens=max_tokens
        )

    def classify(self, query: str) -> Strategy:
        result = self._client.create(
            response_model=RouterClassification,
            messages=[
                {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
                {"role": "user", "content": query},
            ],
        )
        return result.strategy


class CascadingRouter:
    """Production-shaped two-tier router: SemanticRouter (free, instant) handles
    everything it's confident about; only the low-confidence minority gets escalated
    to a real LLM call (`llm_classifier`), instead of SemanticRouter's own silent
    default-to-FACTUAL.

    Every escalation is appended to `log_path` as JSONL: {query, the TF-IDF tier's
    per-class scores, what the LLM decided}. The intended workflow is to periodically
    read that log, pick out queries whose LLM verdict looks right and representative,
    and fold them into `PROTOTYPES` -- growing Tier 1's coverage so fewer future
    queries need Tier 2 at all. `escalation_rate` tracks what fraction of traffic is
    currently paying for an LLM call, so that improvement is directly measurable.

    With `llm_classifier=None` (the default), this behaves exactly like a bare
    `SemanticRouter` -- no API key, no escalation, no log writes -- so it's a safe
    drop-in wherever `SemanticRouter` is used today.
    """

    def __init__(
        self,
        semantic_router: SemanticRouter | None = None,
        llm_classifier: LLMRouteClassifier | None = None,
        log_path: str | Path | None = None,
    ):
        self.semantic_router = semantic_router or SemanticRouter()
        self.llm_classifier = llm_classifier
        self.log_path = Path(log_path) if log_path else None
        self.total_routed = 0
        self.total_escalated = 0

    def route(self, query: str) -> RouteDecision:
        self.total_routed += 1
        decision = self.semantic_router.route(query)

        if not decision.used_default_fallback or self.llm_classifier is None:
            return decision

        self.total_escalated += 1
        llm_strategy = self.llm_classifier.classify(query)
        decision = replace(decision, strategy=llm_strategy, escalated_to_llm=True)
        self._log(query, decision)
        return decision

    @property
    def escalation_rate(self) -> float:
        return self.total_escalated / self.total_routed if self.total_routed else 0.0

    def _log(self, query: str, decision: RouteDecision) -> None:
        if self.log_path is None:
            return
        entry = {
            "query": query,
            "tfidf_scores": {s.value: v for s, v in decision.scores.items()},
            "llm_strategy": decision.strategy.value,
        }
        with self.log_path.open("a") as f:
            f.write(json.dumps(entry) + "\n")
