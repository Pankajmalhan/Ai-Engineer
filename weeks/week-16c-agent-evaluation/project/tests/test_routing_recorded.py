"""The 30-query routing dataset and the committed run of the REAL Week 14 supervisor (keyword classifier)."""

from collections import Counter

from agent_eval.datasets import RUNS, load_routing, routings_from
from agent_eval.metrics import handoff_accuracy
from agent_eval.trajectory import read_jsonl

ITEMS = load_routing()
TRAJS = read_jsonl(RUNS / "w14_heuristic.jsonl")


def test_dataset_is_30_balanced_unique_queries():
    assert len(ITEMS) == 30 and len({i.id for i in ITEMS}) == 30 and len({i.query for i in ITEMS}) == 30
    assert Counter(i.expected for i in ITEMS) == {"code": 10, "rules": 10, "domain": 10}


def test_the_week_14_queries_are_a_separate_subset_so_overfitting_can_show():
    assert Counter(i.subset for i in ITEMS) == {"w14": 10, "new": 20}
    ambiguous = [i for i in ITEMS if i.ambiguous]
    assert len(ambiguous) == 2 and all(i.clarification for i in ambiguous) and all(i.subset == "w14" for i in ambiguous)


def test_every_reference_tool_call_is_the_retriever_for_the_expected_label():
    tool = {"code": "search_code", "rules": "lookup_rules", "domain": "search_domain_docs"}
    assert all([c.name for c in i.reference_tool_calls] == [tool[i.expected]] for i in ITEMS)


def test_the_recorded_run_covers_exactly_the_dataset():
    assert [t.id for t in TRAJS] == [i.id for i in ITEMS]
    assert all(t.meta["system"] == "week-14-supervisor" and t.meta["classifier"] == "heuristic" for t in TRAJS)


def test_each_recorded_run_called_the_retriever_of_the_route_it_chose():
    tool = {"code": "search_code", "rules": "lookup_rules", "domain": "search_domain_docs"}
    for t in TRAJS:
        assert t.tool_names() == [tool[t.meta["routed_to"]]], t.id
        assert t.handoffs == [f"{t.meta['routed_to']}_agent"]


def test_headline_numbers_of_the_recorded_baseline():
    rep = handoff_accuracy(routings_from(TRAJS))
    assert (rep.n, round(rep.accuracy * 30)) == (30, 23)
    assert rep.accuracy_by_subset == {"w14": 1.0, "new": 0.65}
    assert rep.recall_by_label == {"code": 0.7, "rules": 0.6, "domain": 1.0}


def test_the_baseline_overfits_its_own_ten_queries():
    """Week 14's README warned that 10/10 was flattering. Twenty fresh queries put a number on it."""
    by = handoff_accuracy(routings_from(TRAJS)).accuracy_by_subset
    assert by["w14"] - by["new"] >= 0.3


def test_when_unsure_the_baseline_falls_back_to_domain():
    """Every low-confidence guess that was wrong was 'domain' -- a systematic bias, visible in the confusion matrix."""
    rep = handoff_accuracy(routings_from(TRAJS))
    wrong_and_unsure = [r for r in rep.misroutes if (r.first_confidence or 1) <= 0.2]
    assert wrong_and_unsure and all(r.routed_to == "domain" for r in wrong_and_unsure)
    assert sum(row.get("domain", 0) for row in rep.confusion.values()) == 16  # 10 true domain + 6 misrouted into it
