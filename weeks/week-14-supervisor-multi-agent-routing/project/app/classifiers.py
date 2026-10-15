"""The supervisor's brain: anything that turns a query into a ``Route``.

Two interchangeable implementations behind one tiny interface (``classify(query) -> Route``):

* ``LLMClassifier`` -- the real thing. A chat model constrained to the ``Route`` schema via
  ``with_structured_output``. Needs an API key.
* ``HeuristicClassifier`` -- a deterministic keyword baseline. It exists so the graph and the
  routing eval run offline, and so you have a number to beat: if the LLM can't out-route a
  keyword list, the LLM isn't earning its latency and cost.

The graph only depends on the interface, which is also why tests can script a classifier.
"""

from __future__ import annotations

import re
from typing import Protocol

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.schemas import CATEGORIES, Route


class Classifier(Protocol):
    def classify(self, query: str) -> Route: ...


SUPERVISOR_PROMPT = """You route questions from software engineers to exactly one specialist.

- code:   where/how something is implemented in the codebase -- functions, classes, files, modules,
          stack traces, call sites, refactoring, "show me the code for ...".
- rules:  what is allowed or required -- coding standards, lint rules, security policy, review
          and release process, naming conventions, "must/should/can we ...".
- domain: what a business concept means or how the product behaves -- glossary terms, billing,
          onboarding, customer-facing behaviour, "what is ...", "how does ... work for a customer".

Return the category and a calibrated confidence in [0, 1]. If the question could reasonably
belong to two specialists, or is too vague to tell, give a LOW confidence (below 0.6) rather than
guessing. Do not answer the question."""


class LLMClassifier:
    def __init__(self, llm: BaseChatModel):
        self._structured = llm.with_structured_output(Route)

    def classify(self, query: str) -> Route:
        result = self._structured.invoke([SystemMessage(content=SUPERVISOR_PROMPT), HumanMessage(content=query)])
        # with_structured_output(PydanticModel) returns the model; be defensive about dicts.
        return result if isinstance(result, Route) else Route.model_validate(result)


# Keyword evidence per category. Deliberately generic (not fitted to the eval set).
_PATTERNS: dict[str, list[str]] = {
    "code": [
        r"\bfunctions?\b", r"\bclass(es)?\b", r"\bmodules?\b", r"\bimplement(ed|s|ation)?\b",
        r"\bsource\b", r"\bfiles?\b", r"\.py\b|\.ts\b|\.js\b", r"\bstack ?trace\b", r"\bexception\b",
        r"\brefactor\w*\b", r"\bcall(s|ed|ers?)\b", r"\bendpoint\b", r"\bimport(s|ed)?\b", r"\bbug\b",
        r"\bwhere is\b", r"\bgrep\b", r"\brepo(sitory)?\b",
    ],
    "rules": [
        r"\ballowed\b", r"\bpolic(y|ies)\b", r"\bstandards?\b", r"\blint\w*\b", r"\bconvention\b",
        r"\bguidelines?\b", r"\bmust\b", r"\bshould (we|i)\b", r"\bcompl(y|iance|iant)\b",
        r"\brequired?\b", r"\bnaming\b", r"\bapprov(al|ed|e)\b", r"\bcode review\b", r"\bforbidden\b",
        r"\bmerge\b", r"\brules?\b",
    ],
    "domain": [
        r"\bwhat is\b", r"\bwhat does\b.*\bmean\b", r"\bmeaning\b", r"\bglossary\b", r"\bbilling\b",
        r"\binvoices?\b", r"\bcustomers?\b", r"\bonboarding\b", r"\bsubscriptions?\b", r"\bplans?\b",
        r"\bpricing\b", r"\bfree tier\b", r"\baccount\b", r"\bterm\b", r"\bdefin(e|ition)\b",
    ],
}
_COMPILED = {c: [re.compile(p, re.IGNORECASE) for p in pats] for c, pats in _PATTERNS.items()}


class HeuristicClassifier:
    """Confidence = how one-sided the evidence is, discounted when there is little of it.

    * no evidence       -> 0.2 (a coin flip dressed up as an answer; default guess "domain")
    * one clean match   -> 0.75
    * two+ clean matches-> 1.0
    * evidence split between categories -> proportionally lower, usually < 0.6 => ask the human
    """

    def classify(self, query: str) -> Route:
        scores = {c: sum(1 for p in pats if p.search(query)) for c, pats in _COMPILED.items()}
        total = sum(scores.values())
        if total == 0:
            return Route(category="domain", confidence=0.2, reasoning="no keyword evidence for any category")
        top = max(CATEGORIES, key=lambda c: (scores[c], -CATEGORIES.index(c)))
        share = scores[top] / total
        evidence = min(1.0, total / 2)
        confidence = round(share * (0.5 + 0.5 * evidence), 2)
        return Route(category=top, confidence=confidence, reasoning=f"keyword scores {scores}")
