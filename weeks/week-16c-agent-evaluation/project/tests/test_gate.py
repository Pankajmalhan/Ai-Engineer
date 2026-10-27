"""The deterministic CI gate: passes on the recorded baseline, fails when routing degrades."""

import pytest

from agent_eval.datasets import RUNS, load_routing
from agent_eval.gate import HANDOFF_ACCURACY_MIN, HANDOFF_NEW_SUBSET_MIN, TOOL_CALL_F1_MIN, routing_gate
from agent_eval.ragas_metrics import score_tool_calls_sync
from agent_eval.trajectory import ToolCall, read_jsonl

TRAJS = read_jsonl(RUNS / "w14_heuristic.jsonl")


def degrade(trajectories, n_wrong):
    """The 'deliberately bad change': a router that sends the first n queries to the wrong place."""
    out = []
    for i, t in enumerate(trajectories):
        t = t.model_copy(deep=True)
        if i < n_wrong:
            wrong = "rules" if t.meta["expected"] != "rules" else "code"
            t.meta["routed_to"] = wrong
        out.append(t)
    return out


def test_recorded_baseline_passes_the_gate():
    _, gates = routing_gate(TRAJS)
    assert all(g.passed for g in gates), [str(g) for g in gates]


def test_a_regressed_router_fails_the_gate():
    _, gates = routing_gate(degrade(TRAJS, 30))
    assert not any(g.passed for g in gates)


def test_the_gate_is_sensitive_to_a_modest_regression():
    """Baseline 23/30 = 0.767 vs a floor of 0.75: losing two more queries must trip it."""
    ok = routing_gate(degrade(TRAJS, 0))[1][0]
    worse = routing_gate([t for t in degrade(TRAJS, 0)])[0].accuracy
    assert ok.passed and worse >= HANDOFF_ACCURACY_MIN
    broken = degrade(TRAJS[10:], 0)  # drop the 10 easy w14 queries ... then regress two correct ones
    correct = [i for i, t in enumerate(broken) if t.meta["routed_to"] == t.meta["expected"]][:2]
    for i in correct:
        broken[i].meta["routed_to"] = "rules" if broken[i].meta["expected"] != "rules" else "code"
    assert not routing_gate(broken)[1][1].passed  # 'new' subset falls below its floor


def test_the_new_subset_floor_is_what_catches_overfitting_to_the_old_queries():
    only_old_correct = degrade(TRAJS[10:], 20)  # everything new is wrong, old ten untouched
    report, gates = routing_gate(TRAJS[:10] + only_old_correct)
    assert report.accuracy_by_subset["w14"] == 1.0 and report.accuracy_by_subset["new"] == 0.0
    assert not gates[1].passed


def test_thresholds_sit_just_under_the_recorded_baseline():
    report, _ = routing_gate(TRAJS)
    assert HANDOFF_ACCURACY_MIN <= report.accuracy < HANDOFF_ACCURACY_MIN + 0.05
    assert HANDOFF_NEW_SUBSET_MIN <= report.accuracy_by_subset["new"] < HANDOFF_NEW_SUBSET_MIN + 0.1


def test_ragas_tool_call_f1_gate_on_the_recorded_run():
    items = {i.id: i for i in load_routing()}
    f1 = score_tool_calls_sync([(t, items[t.id].reference_tool_calls) for t in TRAJS]).mean_f1
    assert f1 >= TOOL_CALL_F1_MIN


def test_ragas_tool_call_f1_gate_fails_on_a_regressed_run():
    items = {i.id: i for i in load_routing()}
    bad = degrade(TRAJS, 30)
    for t in bad:  # the tool called follows the route
        t.tool_calls = [ToolCall(name={"code": "search_code", "rules": "lookup_rules", "domain": "search_domain_docs"}[t.meta["routed_to"]], args={"k": 3})]
    f1 = score_tool_calls_sync([(t, items[t.id].reference_tool_calls) for t in bad]).mean_f1
    assert f1 < TOOL_CALL_F1_MIN
