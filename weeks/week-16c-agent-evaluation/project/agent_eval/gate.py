"""CI gate: thresholds on the deterministic metrics, evaluated over recorded runs.

The levels are set just under what the committed Week 14 keyword baseline actually scores
(data/runs/w14_heuristic.jsonl), so the gate passes today and fails if routing gets worse. They are a
regression floor, not a target: once an LLM classifier is recorded, raise them to its numbers.
"""

from __future__ import annotations

from dataclasses import dataclass

from agent_eval.metrics import HandoffReport, handoff_accuracy
from agent_eval.datasets import routings_from
from agent_eval.trajectory import Trajectory

HANDOFF_ACCURACY_MIN = 0.75  # baseline: 23/30 = 0.767
HANDOFF_NEW_SUBSET_MIN = 0.60  # baseline: 13/20 = 0.65 -- the held-out-ish queries; the honest number
TOOL_CALL_F1_MIN = 0.75  # RAGAS ToolCallF1 mean over the routing set; baseline 0.767 (a miss scores 0)


@dataclass
class GateResult:
    name: str
    value: float
    minimum: float

    @property
    def passed(self) -> bool:
        return self.value >= self.minimum

    def __str__(self) -> str:
        return f"{'PASS' if self.passed else 'FAIL'} {self.name}: {self.value:.3f} (min {self.minimum:.2f})"


def routing_gate(trajectories: list[Trajectory]) -> tuple[HandoffReport, list[GateResult]]:
    report = handoff_accuracy(routings_from(trajectories))
    results = [GateResult("handoff accuracy", report.accuracy, HANDOFF_ACCURACY_MIN)]
    if "new" in report.accuracy_by_subset:
        results.append(GateResult("handoff accuracy (new queries)", report.accuracy_by_subset["new"], HANDOFF_NEW_SUBSET_MIN))
    return report, results
