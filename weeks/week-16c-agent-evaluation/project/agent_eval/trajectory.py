"""The framework-neutral record of one agent run -- the single contract everything here consumes.

Week 14's graph, Week 16b's supervisor loop and its Deep Agent each live in their own project with
their own ``app`` package, so they cannot be imported side by side. Each is run by a small *bridge*
(``bridges/``) inside its own environment, which prints one ``Trajectory`` as a JSON line. Evaluation
then works on those lines -- recorded, diffable, replayable in CI without re-running the agent.

A trajectory is the *path*, not just the destination: every tool call in order (nested sub-agent calls
included), who the orchestrator delegated to, and the end state the run left behind.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    name: str
    args: dict[str, Any] = Field(default_factory=dict)


class Trajectory(BaseModel):
    id: str  # dataset item / task id
    user_input: str
    tool_calls: list[ToolCall] = Field(default_factory=list)  # every call, in order, sub-agents' included
    handoffs: list[str] = Field(default_factory=list)  # delegation targets in order (specialist / sub-agent names)
    final_output: str = ""
    files: dict[str, str] = Field(default_factory=dict)  # virtual filesystem at the end of the run
    llm_calls: int | None = None  # all model calls, nested ones included
    total_tokens: int | None = None  # None = the model did not report usage (e.g. scripted)
    error: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)  # arch, trial, classifier, ...

    @property
    def report(self) -> str:
        """Everything the run produced for the user: saved files first, then the final message."""
        return "\n\n".join([*self.files.values(), self.final_output]).strip()

    def tool_names(self) -> list[str]:
        return [c.name for c in self.tool_calls]


def read_jsonl(path: str | Path) -> list[Trajectory]:
    return [Trajectory.model_validate_json(line) for line in Path(path).read_text().splitlines() if line.strip()]


def write_jsonl(path: str | Path, trajectories: Iterable[Trajectory]) -> None:
    Path(path).write_text("".join(t.model_dump_json() + "\n" for t in trajectories))


def parse_jsonl_stream(text: str) -> Iterator[Trajectory]:
    """Parse a bridge's stdout: JSON lines, ignoring any non-JSON noise a library printed."""
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                yield Trajectory.model_validate(json.loads(line))
            except ValueError:
                continue
