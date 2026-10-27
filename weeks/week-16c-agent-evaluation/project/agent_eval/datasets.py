"""Load the committed datasets in ``data/`` and turn recorded trajectories into scorable rows."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from agent_eval.end_state import Task
from agent_eval.metrics import LABELS, Routing
from agent_eval.trajectory import ToolCall, Trajectory

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RUNS = DATA / "runs"


class RoutingItem(BaseModel):
    """A Week-5-shaped eval row (``user_input`` + ``reference`` + ``reference_tool_calls``) for the Week 14 supervisor."""

    id: str
    query: str
    expected: Literal["code", "rules", "domain"]
    subset: str
    ambiguous: bool = False
    clarification: str | None = None
    reference: str
    reference_tool_calls: list[ToolCall] = Field(min_length=1)


def load_routing(path: Path = DATA / "routing_30.json") -> list[RoutingItem]:
    return [RoutingItem.model_validate(row) for row in json.loads(path.read_text())]


def load_tasks(name: Literal["tasks_10", "hard_5"]) -> list[Task]:
    return [Task.model_validate(row) for row in json.loads((DATA / f"{name}.json").read_text())]


def routings_from(trajectories: list[Trajectory]) -> list[Routing]:
    """Rebuild labelled routing results from what the Week 14 bridge recorded in ``meta``."""
    out = []
    for t in trajectories:
        m = t.meta
        if m.get("expected") not in LABELS:
            raise ValueError(f"{t.id}: trajectory has no routing labels in meta")
        out.append(Routing(
            id=t.id, expected=m["expected"], routed_to=m.get("routed_to") or "(none)", subset=m.get("subset", "all"),
            first_pass=m.get("first_pass"), first_confidence=m.get("first_confidence"),
            asked=bool(m.get("asked")), ambiguous=bool(m.get("ambiguous")),
        ))
    return out
