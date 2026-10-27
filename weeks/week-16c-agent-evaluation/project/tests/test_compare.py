"""Supervisor-vs-Deep-Agent summary: success, reliability, efficiency, cost -- from hand-built and recorded trajectories."""

import pytest

from agent_eval.compare import evaluate_runs, format_summary, summarize
from agent_eval.datasets import RUNS, load_tasks
from agent_eval.end_state import Check, Task
from agent_eval.trajectory import read_jsonl
from tests.conftest import traj

TASKS = [
    Task(id="a", user_goal="g", sources_needed=1, required_end_state=[Check(kind="report_matches", description="x", pattern="ALPHA")]),
    Task(id="b", user_goal="g", sources_needed=3, required_end_state=[Check(kind="report_matches", description="x", pattern="BETA")]),
]


def run(task, arch, trial, report, handoffs, **kw):
    return traj(task, report, handoffs=handoffs, meta={"arch": arch, "trial": trial}, **kw)


def by_arch(summaries):
    return {s.arch: s for s in summaries}


def test_success_checks_delegation_efficiency_and_cost_per_architecture():
    runs = [
        run("a", "sup", 0, "ALPHA", ["code"], llm_calls=2, total_tokens=100),
        run("b", "sup", 0, "nope", ["code", "rules", "domain"], llm_calls=4, total_tokens=300),
        run("a", "deep", 0, "ALPHA", ["x", "y", "z"], llm_calls=10, total_tokens=900),
        run("b", "deep", 0, "BETA", ["x", "y", "z"], llm_calls=14, total_tokens=1500),
    ]
    s = by_arch(summarize(runs, TASKS))
    assert (s["sup"].success_rate, s["deep"].success_rate) == (0.5, 1.0)
    assert s["sup"].delegation_efficiency == 1.0  # needed 1 -> made 1; needed 3 -> made 3
    assert s["deep"].delegation_efficiency == pytest.approx((1 / 3 + 1.0) / 2)  # it used 3 delegations for a 1-source task
    assert (s["sup"].llm_calls, s["deep"].llm_calls) == (3.0, 12.0)
    assert (s["sup"].tokens, s["deep"].tokens) == (200.0, 1200.0)
    assert s["sup"].success_by_sources == {1: 1.0, 3: 0.0}


def test_reliability_pass_hat_k_needs_every_task_to_have_k_trials():
    runs = [run(t, "deep", i, "ALPHA BETA" if ok else "-", ["x"]) for t, trials in {"a": [True, True, True], "b": [True, False, True]}.items() for i, ok in enumerate(trials)]
    ph = by_arch(summarize(runs, TASKS))["deep"].pass_hat
    assert set(ph) == {1, 2, 3}
    assert ph[1] == pytest.approx((1 + 2 / 3) / 2)
    assert ph[3] == pytest.approx((1 + 0) / 2)
    assert ph[1] > ph[2] > ph[3]


def test_uneven_trial_counts_cap_k_at_the_smallest():
    runs = [run("a", "x", 0, "ALPHA", ["h"]), run("a", "x", 1, "ALPHA", ["h"]), run("b", "x", 0, "BETA", ["h"])]
    assert set(by_arch(summarize(runs, TASKS))["x"].pass_hat) == {1}


def test_a_crashed_run_counts_as_a_failure_and_is_reported():
    runs = [run("a", "deep", 0, "ALPHA", ["x"], error="GraphRecursionError"), run("b", "deep", 0, "BETA", ["x"])]
    s = by_arch(summarize(runs, TASKS))["deep"]
    assert s.errors == 1 and s.success_rate == 0.5


def test_missing_token_counts_show_as_none_not_zero():
    runs = [run("a", "sup", 0, "ALPHA", ["c"], llm_calls=1), run("b", "sup", 0, "BETA", ["c"], llm_calls=1)]
    s = by_arch(summarize(runs, TASKS))["sup"]
    assert s.tokens is None and s.llm_calls == 1.0


def test_an_unknown_task_id_is_an_error():
    with pytest.raises(KeyError, match="zzz"):
        evaluate_runs([run("zzz", "sup", 0, "x", [])], TASKS)


def test_summary_text_shows_the_columns_and_na_for_unreported_tokens():
    text = format_summary(summarize([run("a", "sup", 0, "ALPHA", ["c"], llm_calls=2)], TASKS))
    assert "sup" in text and "n/a" in text and "pass^1=1.00" in text and "1-src=100%" in text


# ---- the recorded offline structure sample (scripted Week 16b oracle on task t08) ----


def test_the_recorded_offline_t08_runs_summarise_end_to_end():
    runs = read_jsonl(RUNS / "w16b_offline_t08.jsonl")
    summaries = by_arch(summarize(runs, load_tasks("tasks_10")))
    assert set(summaries) == {"supervisor", "deep"}
    assert all(s.success_rate == 1.0 and s.tokens is None for s in summaries.values())  # scripted: by construction, no usage


def test_the_deep_agent_trajectory_exposes_nested_calls_the_lead_thread_hides():
    deep = next(t for t in read_jsonl(RUNS / "w16b_offline_t08.jsonl") if t.meta["arch"] == "deep")
    names = deep.tool_names()
    assert names.count("task") == 3 and names[0] == "write_todos" and names[-1] == "write_file"
    assert {"search_code", "read_code", "lookup_rules", "search_domain_docs"} <= set(names)  # sub-agents' own calls
    assert deep.handoffs == ["code-researcher", "rules-checker", "policy-analyst"]
    assert "/audit.md" in deep.files and deep.llm_calls == 14


def test_delegation_counts_agree_between_the_two_architectures_on_the_same_three_source_task():
    runs = {t.meta["arch"]: t for t in read_jsonl(RUNS / "w16b_offline_t08.jsonl")}
    assert len(runs["supervisor"].handoffs) == len(runs["deep"].handoffs) == 3
