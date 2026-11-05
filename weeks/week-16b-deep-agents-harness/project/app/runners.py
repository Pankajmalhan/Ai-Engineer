"""Run each architecture on the audit task and return the same shaped result for both."""

from __future__ import annotations

from dataclasses import dataclass, field

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage

from app.deep import build_deep_agent
from app.metrics import Metrics, RunMetrics
from app.supervisor import Planner, build_supervisor_graph, initial_state
from app.task import DEEP_SUFFIX, TASK, AuditScore, score_audit

REPORT_PATH = "/audit.md"
RECURSION_LIMIT = 100


@dataclass
class RunResult:
    name: str
    report: str
    score: AuditScore
    metrics: Metrics
    report_source: str  # "final-message" (supervisor) | "file" | "final-message (not saved)" | "none"
    notes: list[str] = field(default_factory=list)  # specialists run / todos written / sub-agent calls
    error: str | None = None


def _failed(name: str, exc: Exception, run: RunMetrics) -> RunResult:
    # A crash is data, not a reason to abort the comparison (e.g. the recursion limit).
    return RunResult(name, "", score_audit(""), run.finish([]), "none", error=f"{type(exc).__name__}: {exc}")


def run_supervisor(name: str, planner: Planner, writer: BaseChatModel, *, max_hops: int) -> RunResult:
    graph = build_supervisor_graph(planner, writer, max_hops=max_hops)
    run = RunMetrics()
    try:
        out = graph.invoke(initial_state(TASK), config={"callbacks": [run], "recursion_limit": RECURSION_LIMIT})
    except Exception as exc:
        return _failed(name, exc, run)
    report = str(out["messages"][-1].content)
    for category in out["trail"]:  # specialists are plain functions, so the callback never sees them
        run.metrics.tool_calls[f"{category}_agent"] += 1
    return RunResult(
        name, report, score_audit(report), run.finish(out["messages"]), "final-message",
        notes=[f"specialists: {' -> '.join(out['trail']) or '(none)'}"],
    )


def run_deep(name: str, model: BaseChatModel, *, planning: bool = True, subagent_models=None) -> RunResult:
    from deepagents.backends.utils import file_data_to_string

    agent = build_deep_agent(model, planning=planning, subagent_models=subagent_models)
    run = RunMetrics()
    try:
        out = agent.invoke(
            {"messages": [HumanMessage(content=TASK + DEEP_SUFFIX)]},
            config={"callbacks": [run], "recursion_limit": RECURSION_LIMIT},
        )
    except Exception as exc:
        return _failed(name, exc, run)

    files = out.get("files") or {}
    final = str(out["messages"][-1].content)
    if REPORT_PATH in files:
        report, source = file_data_to_string(files[REPORT_PATH]), "file"
    else:  # failure mode: the agent answered in chat and never saved the deliverable
        report, source = final, "final-message (not saved)"
    todos = out.get("todos") or []
    notes = [
        f"files written: {sorted(files) or '(none)'}",
        f"todos: {len(todos)} ({sum(t.get('status') == 'completed' for t in todos)} completed)" if planning else "planning off",
        f"sub-agent calls: {run.metrics.tool_calls.get('task', 0)}",
    ]
    return RunResult(name, report, score_audit(report), run.finish(out["messages"]), source, notes=notes)
