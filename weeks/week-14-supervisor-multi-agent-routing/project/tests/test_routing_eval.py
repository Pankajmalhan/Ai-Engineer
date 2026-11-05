from app.classifiers import HeuristicClassifier
from app.routing_eval import CASES, run_eval, summarize
from app.schemas import Route


def test_there_are_ten_cases_covering_all_three_categories_and_ambiguity():
    assert len(CASES) == 10
    assert {c.expected for c in CASES} == {"code", "rules", "domain"}
    assert sum(c.ambiguous for c in CASES) == 2


def test_heuristic_baseline_routes_all_ten_end_to_end():
    results = run_eval(HeuristicClassifier())
    wrong = [(r.case.query, r.case.expected, r.routed_to) for r in results if not r.correct]
    assert not wrong, wrong
    stats = summarize(results)
    assert stats["accuracy"] == 1.0
    assert stats["clarified_correctly"] == 1.0  # asked on the 2 ambiguous cases, on none of the 8 others
    assert stats["first_pass_accuracy_clear"] == 1.0


class _AlwaysCode:
    def classify(self, query: str) -> Route:
        return Route(category="code", confidence=0.95)


def test_eval_actually_discriminates_a_constant_router_scores_poorly():
    results = run_eval(_AlwaysCode())  # never asks, never varies
    stats = summarize(results)
    assert stats["accuracy"] < 0.5
    assert stats["clarified_correctly"] == 0.8  # right on the 8 clear cases, misses both ambiguous ones
