"""Routing accuracy over 10 hand-written queries, run end to end through the real graph.

Each case says which agent *should* answer. Eight are clear-cut; two are deliberately
ambiguous and carry the clarification a human would give, so the eval exercises the
interrupt -> resume path too. Three numbers come out:

* accuracy            -- did the final agent match the expected one?
* clarified correctly -- did the supervisor ask on exactly the ambiguous cases (no more, no less)?
* first-pass accuracy -- on the clear-cut cases, was the supervisor's *own* category right?

Caveat: ten cases is a smoke test, not a benchmark. It catches a broken prompt or router; it
cannot tell you 92% from 95%. Grow the set (and add real production queries) before trusting a number.
"""

from __future__ import annotations

from dataclasses import dataclass

from langgraph.checkpoint.memory import InMemorySaver

from app.classifiers import Classifier
from app.graph import ask, build_graph, resume


@dataclass(frozen=True)
class Case:
    query: str
    expected: str  # "code" | "rules" | "domain"
    ambiguous: bool = False
    clarification: str | None = None  # what the human replies if the supervisor asks


CASES: list[Case] = [
    Case("Where is the refresh_session function implemented?", "code"),
    Case("Show me the stack trace handling in the payments module", "code"),
    Case("Which files import the auth client class?", "code"),
    Case("Are we allowed to commit API keys?", "rules"),
    Case("Does the lint standard require type hints?", "rules"),
    Case("Must every pull request get an approval before merge?", "rules"),
    Case("What is a subscription in our billing system?", "domain"),
    Case("How long does a new customer stay on the free tier during onboarding?", "domain"),
    # Ambiguous: no signal / signal split across agents. Human clarifies.
    Case("Tell me about session refresh", "code", ambiguous=True, clarification="I mean the implementation"),
    Case("Can we merge the function that calls the billing API?", "rules", ambiguous=True, clarification="rules"),
]


@dataclass
class CaseResult:
    case: Case
    routed_to: str  # category the final agent handled
    first_pass: str  # supervisor's first category guess
    first_confidence: float
    asked: bool

    @property
    def correct(self) -> bool:
        return self.routed_to == self.case.expected

    @property
    def clarified_correctly(self) -> bool:
        return self.asked == self.case.ambiguous


def run_case(classifier: Classifier, case: Case, index: int) -> CaseResult:
    graph = build_graph(classifier, checkpointer=InMemorySaver())
    thread = f"eval-{index}"
    turn = ask(graph, case.query, thread)
    asked = turn.interrupted
    first = turn.route
    if asked:
        if case.clarification is None:
            raise RuntimeError(f"supervisor asked about an unambiguous case: {case.query!r}")
        turn = resume(graph, case.clarification, thread)
    routed_to = (turn.agent or "").removesuffix("_agent")
    if not asked:
        first = turn.route
    return CaseResult(case, routed_to, first["category"], first["confidence"], asked)


def run_eval(classifier: Classifier, cases: list[Case] | None = None) -> list[CaseResult]:
    return [run_case(classifier, c, i) for i, c in enumerate(cases or CASES)]


def summarize(results: list[CaseResult]) -> dict[str, float]:
    clear = [r for r in results if not r.case.ambiguous]
    return {
        "accuracy": sum(r.correct for r in results) / len(results),
        "clarified_correctly": sum(r.clarified_correctly for r in results) / len(results),
        "first_pass_accuracy_clear": sum(r.first_pass == r.case.expected for r in clear) / len(clear),
    }
