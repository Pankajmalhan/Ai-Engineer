"""Deterministic agent metrics that RAGAS / DeepEval do not give you for free.

* handoff accuracy -- did the supervisor pick the right specialist (+ confusion matrix, per-label recall)
* delegation efficiency -- sources a task needs / delegations actually made
* pass^k -- tau-bench's reliability metric: P(all k independent trials of a task succeed)
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from math import comb

LABELS = ("code", "rules", "domain")


@dataclass(frozen=True)
class Routing:
    """One labelled query and what the supervisor did with it."""

    id: str
    expected: str
    routed_to: str
    subset: str = "all"
    first_pass: str | None = None  # the supervisor's own first guess, before any human clarification
    first_confidence: float | None = None
    asked: bool = False  # did it interrupt to ask the human?
    ambiguous: bool = False  # was it supposed to?

    @property
    def correct(self) -> bool:
        return self.routed_to == self.expected


@dataclass
class HandoffReport:
    n: int
    accuracy: float
    first_pass_accuracy: float | None
    clarification_accuracy: float  # asked exactly on the ambiguous ones
    recall_by_label: dict[str, float]
    confusion: dict[str, dict[str, int]]  # confusion[expected][routed_to]
    accuracy_by_subset: dict[str, float]
    misroutes: list[Routing] = field(default_factory=list)

    def format(self) -> str:
        lines = [f"handoff accuracy {self.accuracy:.0%} ({round(self.accuracy * self.n)}/{self.n})"]
        if self.first_pass_accuracy is not None:
            lines.append(f"first-pass accuracy {self.first_pass_accuracy:.0%} | asked-when-ambiguous {self.clarification_accuracy:.0%}")
        lines.append("recall: " + ", ".join(f"{k} {v:.0%}" for k, v in self.recall_by_label.items()))
        lines.append("by subset: " + ", ".join(f"{k} {v:.0%}" for k, v in self.accuracy_by_subset.items()))
        routed = sorted({r for row in self.confusion.values() for r in row})
        lines.append("confusion (rows = expected, cols = routed): " + " ".join(f"{r:>7}" for r in routed))
        for exp, row in self.confusion.items():
            lines.append(f"  {exp:<8}" + " ".join(f"{row.get(r, 0):>7}" for r in routed))
        return "\n".join(lines)


def handoff_accuracy(results: list[Routing]) -> HandoffReport:
    if not results:
        raise ValueError("no routing results to score")
    confusion: dict[str, Counter] = defaultdict(Counter)
    by_subset: dict[str, list[bool]] = defaultdict(list)
    for r in results:
        confusion[r.expected][r.routed_to] += 1
        by_subset[r.subset].append(r.correct)
    recall = {lab: confusion[lab][lab] / sum(confusion[lab].values()) for lab in LABELS if confusion[lab]}
    firsts = [r for r in results if r.first_pass is not None]
    return HandoffReport(
        n=len(results),
        accuracy=sum(r.correct for r in results) / len(results),
        first_pass_accuracy=(sum(r.first_pass == r.expected for r in firsts) / len(firsts)) if firsts else None,
        clarification_accuracy=sum(r.asked == r.ambiguous for r in results) / len(results),
        recall_by_label=recall,
        confusion={k: dict(v) for k, v in confusion.items()},
        accuracy_by_subset={k: sum(v) / len(v) for k, v in by_subset.items()},
        misroutes=[r for r in results if not r.correct],
    )


def delegation_efficiency(sources_needed: int, delegations: int) -> float:
    """Minimum delegations a task needs (one per distinct source) / delegations actually made, capped at 1.

    1.0 = no wasted hops. 0.0 = it delegated nothing -- which is *not* efficient, it never consulted a
    source (an agent answering from nothing is a different failure, caught by the end-state checks).
    """
    if delegations <= 0:
        return 0.0
    return min(1.0, sources_needed / delegations)


def pass_hat_k(trials_per_task: list[list[bool]], k: int) -> float:
    """tau-bench's pass^k: the chance that *all* k i.i.d. trials of a random task succeed.

    Per task with n trials and c successes the unbiased estimate is C(c,k)/C(n,k); the result is the
    mean over tasks. pass^1 is plain success rate; pass^k falls fast when an agent is merely
    "usually right", which is the property a production agent needs.
    """
    if k < 1:
        raise ValueError("k must be >= 1")
    if any(len(t) < k for t in trials_per_task):
        raise ValueError(f"every task needs at least k={k} trials")
    if not trials_per_task:
        raise ValueError("no tasks")
    return sum(comb(sum(t), k) / comb(len(t), k) for t in trials_per_task) / len(trials_per_task)
