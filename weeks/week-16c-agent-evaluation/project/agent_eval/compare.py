"""Supervisor loop vs Deep Agent over the same tasks: success, reliability, efficiency, cost.

Everything here is computed from recorded trajectories (meta.arch, meta.trial), so the same code scores
a real-model run, a scripted run, or a hand-built fixture.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from agent_eval.end_state import EndStateResult, Task, evaluate_end_state
from agent_eval.metrics import delegation_efficiency, pass_hat_k
from agent_eval.trajectory import Trajectory

MAX_K = 4


@dataclass
class RunEval:
    trajectory: Trajectory
    task: Task
    end_state: EndStateResult
    delegation_efficiency: float

    @property
    def arch(self) -> str:
        return self.trajectory.meta.get("arch", "?")


@dataclass
class ArchSummary:
    arch: str
    runs: int
    errors: int
    success_rate: float  # pass^1: every end-state check passed
    check_fraction: float  # mean fraction of checks passed -- partial credit
    delegation_efficiency: float
    delegations: float
    tool_calls: float
    llm_calls: float | None
    tokens: float | None
    pass_hat: dict[int, float] = field(default_factory=dict)  # k -> pass^k (only when every task has >= k trials)
    success_by_sources: dict[int, float] = field(default_factory=dict)  # sources_needed -> success rate


def evaluate_runs(trajectories: list[Trajectory], tasks: list[Task]) -> list[RunEval]:
    by_id = {t.id: t for t in tasks}
    out = []
    for traj in trajectories:
        if traj.id not in by_id:
            raise KeyError(f"trajectory {traj.id!r} is not a known task id")
        task = by_id[traj.id]
        out.append(RunEval(traj, task, evaluate_end_state(task, traj), delegation_efficiency(task.sources_needed, len(traj.handoffs))))
    return out


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs)


def _mean_or_none(xs: list) -> float | None:
    xs = [x for x in xs if x is not None]
    return _mean(xs) if xs else None


def summarize(trajectories: list[Trajectory], tasks: list[Task]) -> list[ArchSummary]:
    runs = evaluate_runs(trajectories, tasks)
    groups: dict[str, list[RunEval]] = defaultdict(list)
    for r in runs:
        groups[r.arch].append(r)

    summaries = []
    for arch, rs in sorted(groups.items()):
        per_task: dict[str, list[bool]] = defaultdict(list)
        by_sources: dict[int, list[bool]] = defaultdict(list)
        for r in rs:
            per_task[r.task.id].append(r.end_state.success)
            by_sources[r.task.sources_needed].append(r.end_state.success)
        min_trials = min(len(v) for v in per_task.values())
        summaries.append(ArchSummary(
            arch=arch, runs=len(rs), errors=sum(bool(r.trajectory.error) for r in rs),
            success_rate=_mean([r.end_state.success for r in rs]),
            check_fraction=_mean([r.end_state.fraction for r in rs]),
            delegation_efficiency=_mean([r.delegation_efficiency for r in rs]),
            delegations=_mean([len(r.trajectory.handoffs) for r in rs]),
            tool_calls=_mean([len(r.trajectory.tool_calls) for r in rs]),
            llm_calls=_mean_or_none([r.trajectory.llm_calls for r in rs]),
            tokens=_mean_or_none([r.trajectory.total_tokens for r in rs]),
            pass_hat={k: pass_hat_k(list(per_task.values()), k) for k in range(1, min(min_trials, MAX_K) + 1)},
            success_by_sources={s: _mean(v) for s, v in sorted(by_sources.items())},
        ))
    return summaries


def format_summary(summaries: list[ArchSummary]) -> str:
    def opt(x, fmt="{:.0f}"):
        return "n/a" if x is None else fmt.format(x)

    head = f"{'arch':<12}{'runs':>5}{'err':>4}{'success':>9}{'checks':>8}{'deleg.eff':>10}{'deleg':>6}{'tools':>6}{'llm':>6}{'tokens':>9}"
    lines = [head, "-" * len(head)]
    for s in summaries:
        lines.append(f"{s.arch:<12}{s.runs:>5}{s.errors:>4}{s.success_rate:>9.0%}{s.check_fraction:>8.0%}{s.delegation_efficiency:>10.2f}"
                     f"{s.delegations:>6.1f}{s.tool_calls:>6.1f}{opt(s.llm_calls, '{:.1f}'):>6}{opt(s.tokens):>9}")
    lines.append("")
    lines.append("reliability  " + " | ".join(
        f"{s.arch}: " + " ".join(f"pass^{k}={v:.2f}" for k, v in s.pass_hat.items()) for s in summaries))
    lines.append("success by sources needed  " + " | ".join(
        f"{s.arch}: " + " ".join(f"{n}-src={v:.0%}" for n, v in s.success_by_sources.items()) for s in summaries))
    return "\n".join(lines)
