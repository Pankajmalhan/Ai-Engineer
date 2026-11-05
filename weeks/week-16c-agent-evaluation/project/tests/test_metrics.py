import pytest

from agent_eval.metrics import Routing, delegation_efficiency, handoff_accuracy, pass_hat_k


def r(i, expected, routed, subset="all", **kw):
    return Routing(id=str(i), expected=expected, routed_to=routed, subset=subset, **kw)


# ---- handoff accuracy ----


def test_handoff_accuracy_with_confusion_and_per_label_recall():
    results = [r(1, "code", "code"), r(2, "code", "domain"), r(3, "rules", "rules"), r(4, "rules", "domain"), r(5, "domain", "domain"), r(6, "domain", "domain")]
    rep = handoff_accuracy(results)
    assert rep.n == 6 and rep.accuracy == pytest.approx(4 / 6)
    assert rep.recall_by_label == {"code": 0.5, "rules": 0.5, "domain": 1.0}
    assert rep.confusion["code"] == {"code": 1, "domain": 1}
    assert [m.id for m in rep.misroutes] == ["2", "4"]


def test_subsets_are_reported_separately_so_an_overfit_baseline_is_visible():
    results = [r(1, "code", "code", "w14"), r(2, "rules", "rules", "w14"), r(3, "code", "domain", "new"), r(4, "rules", "code", "new")]
    assert handoff_accuracy(results).accuracy_by_subset == {"w14": 1.0, "new": 0.0}


def test_first_pass_and_clarification_accuracy_are_independent_of_final_accuracy():
    results = [
        r(1, "code", "code", first_pass="domain", asked=True, ambiguous=True),   # asked, right to, fixed by the human
        r(2, "rules", "rules", first_pass="rules", asked=False, ambiguous=False),
        r(3, "domain", "domain", first_pass="domain", asked=True, ambiguous=False),  # asked when it should not have
    ]
    rep = handoff_accuracy(results)
    assert rep.accuracy == 1.0
    assert rep.first_pass_accuracy == pytest.approx(2 / 3)
    assert rep.clarification_accuracy == pytest.approx(2 / 3)


def test_first_pass_is_none_when_it_was_not_recorded():
    assert handoff_accuracy([r(1, "code", "code")]).first_pass_accuracy is None


def test_an_empty_result_set_is_an_error_not_a_vacuous_100_percent():
    with pytest.raises(ValueError):
        handoff_accuracy([])


def test_report_formatting_mentions_the_key_numbers():
    text = handoff_accuracy([r(1, "code", "code", "w14"), r(2, "code", "domain", "new")]).format()
    assert "50%" in text and "w14 100%" in text and "new 0%" in text and "confusion" in text


# ---- delegation efficiency ----


@pytest.mark.parametrize("needed, made, expected", [(3, 3, 1.0), (3, 6, 0.5), (1, 3, pytest.approx(1 / 3)), (2, 1, 1.0), (3, 0, 0.0)])
def test_delegation_efficiency(needed, made, expected):
    assert delegation_efficiency(needed, made) == expected


# ---- pass^k ----


def test_pass_hat_k_matches_the_taubench_definition():
    # one task, 4 trials, 3 succeed: pass^1 = 3/4, pass^2 = C(3,2)/C(4,2) = 1/2, pass^3 = 1/4, pass^4 = 0
    trials = [[True, True, True, False]]
    assert [pass_hat_k(trials, k) for k in (1, 2, 3, 4)] == [0.75, 0.5, 0.25, 0.0]


def test_pass_hat_k_averages_over_tasks():
    assert pass_hat_k([[True, True], [False, False]], 2) == 0.5
    assert pass_hat_k([[True, True], [True, False]], 1) == 0.75


def test_reliability_never_rises_with_k_and_an_always_right_agent_stays_at_one():
    flaky = [[True, False, True, True], [True, True, True, False], [False, True, True, True]]
    values = [pass_hat_k(flaky, k) for k in (1, 2, 3, 4)]
    assert values == sorted(values, reverse=True) and values[0] > values[-1]
    assert [pass_hat_k([[True] * 4], k) for k in (1, 2, 3, 4)] == [1.0] * 4


def test_pass_hat_k_rejects_too_few_trials_and_bad_k():
    with pytest.raises(ValueError, match="at least k=3"):
        pass_hat_k([[True, True]], 3)
    with pytest.raises(ValueError):
        pass_hat_k([[True]], 0)
    with pytest.raises(ValueError):
        pass_hat_k([], 1)
