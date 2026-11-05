"""tau-bench-style success: a task is a user goal plus the *end state* a correct run must leave behind.

tau-bench (Sierra) scores an agent by comparing the database after the conversation with the goal
state, not by reading the transcript. Here the "database" is the run's observable footprint: the
report text, the files it saved, which tools it called with what arguments, who it delegated to.
Checks are declarative data so a task can be reviewed (and a wrong check fixed) without touching code.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

from agent_eval.trajectory import Trajectory

CheckKind = Literal[
    "report_matches",  # regex must match somewhere in the report
    "report_not_matches",  # regex must NOT match (fabrication / forbidden claim)
    "file_written",  # a file must exist at `path`
    "tool_called",  # tool `name` must have been called
    "tool_not_called",
    "tool_args_not_matching",  # no tool call's args may match regex `pattern` (constraint following)
    "delegated_to",  # orchestrator must have handed off to `name`
    "max_tool_calls",  # at most `n` tool calls in total (budget)
]


class Check(BaseModel):
    kind: CheckKind
    description: str
    pattern: str | None = None
    name: str | None = None
    path: str | None = None
    n: int | None = None

    def passed(self, t: Trajectory) -> bool:
        match self.kind:
            case "report_matches":
                return bool(re.search(self._need(self.pattern), t.report, re.IGNORECASE))
            case "report_not_matches":
                return not re.search(self._need(self.pattern), t.report, re.IGNORECASE)
            case "file_written":
                return self._need(self.path) in t.files
            case "tool_called":
                return self._need(self.name) in t.tool_names()
            case "tool_not_called":
                return self._need(self.name) not in t.tool_names()
            case "tool_args_not_matching":
                pat = self._need(self.pattern)
                return not any(re.search(pat, str(c.args), re.IGNORECASE) for c in t.tool_calls)
            case "delegated_to":
                return self._need(self.name) in t.handoffs
            case "max_tool_calls":
                return len(t.tool_calls) <= self._need(self.n)
        raise AssertionError(self.kind)  # pragma: no cover

    @staticmethod
    def _need(value):
        if value is None:
            raise ValueError("check is missing a required field for its kind")
        return value


class Task(BaseModel):
    id: str
    user_goal: str
    required_end_state: list[Check]
    sources_needed: int = Field(ge=1, le=3, description="How many distinct sources (code/rules/domain) a correct answer needs.")
    tags: list[str] = Field(default_factory=list)


class EndStateResult(BaseModel):
    task_id: str
    outcomes: list[tuple[str, bool]]

    @property
    def success(self) -> bool:
        return all(ok for _, ok in self.outcomes)

    @property
    def fraction(self) -> float:
        return sum(ok for _, ok in self.outcomes) / len(self.outcomes) if self.outcomes else 0.0

    @property
    def failed(self) -> list[str]:
        return [d for d, ok in self.outcomes if not ok]


def evaluate_end_state(task: Task, trajectory: Trajectory) -> EndStateResult:
    # A run that crashed has no trustworthy end state, whatever partial text it left.
    if trajectory.error:
        return EndStateResult(task_id=task.id, outcomes=[(f"run errored: {trajectory.error}", False)])
    return EndStateResult(task_id=task.id, outcomes=[(c.description, c.passed(trajectory)) for c in task.required_end_state])
