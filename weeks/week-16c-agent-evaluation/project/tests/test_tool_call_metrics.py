"""RAGAS and DeepEval tool-call metrics on the same trajectories -- where they agree and, more usefully, where they don't."""

import pytest

from agent_eval.datasets import RUNS, load_routing
from agent_eval.deepeval_metrics import NoJudge, tool_correctness
from agent_eval.metrics import handoff_accuracy
from agent_eval.datasets import routings_from
from agent_eval.ragas_metrics import score_tool_calls_sync, to_ragas_messages
from agent_eval.trajectory import ToolCall, read_jsonl
from tests.conftest import traj


def tc(name, **args):
    return ToolCall(name=name, args=args)


def three(actual_calls, reference, *, ordering=False):
    t = traj(calls=[(c.name, c.args) for c in actual_calls])
    ragas = score_tool_calls_sync([(t, reference)])
    return ragas.accuracy[0], ragas.f1[0], tool_correctness([(t, reference)], consider_ordering=ordering)[0]


REF = [tc("search_code", k=3)]


def test_exact_match_is_1_everywhere():
    assert three([tc("search_code", k=3)], REF) == (1.0, 1.0, 1.0)


def test_wrong_tool_is_0_everywhere():
    assert three([tc("lookup_rules", k=3)], REF) == (0.0, 0.0, 0.0)


def test_an_extra_call_gets_three_different_verdicts():
    accuracy, f1, correctness = three([tc("search_code", k=3), tc("lookup_rules", k=3)], REF)
    assert accuracy == 0.0  # strict: the call list must be exactly the reference
    assert f1 == pytest.approx(2 / 3, abs=1e-3)  # precision 1/2, recall 1 (RAGAS rounds to 4 d.p.)
    assert correctness == 1.0  # DeepEval: every expected tool was called; extras are not penalised


def test_a_wrong_argument_fails_ragas_but_not_deepeval_which_compares_names_by_default():
    accuracy, f1, correctness = three([tc("search_code", k=5)], REF)
    assert (accuracy, f1) == (0.0, 0.0) and correctness == 1.0


def test_order_matters_to_accuracy_and_to_ordering_aware_deepeval_but_not_to_f1():
    ref = [tc("a"), tc("b")]
    swapped = [tc("b"), tc("a")]
    accuracy, f1, correctness = three(swapped, ref)
    assert (accuracy, f1, correctness) == (0.0, 1.0, 1.0)
    assert three(swapped, ref, ordering=True)[2] == 0.5


def test_no_tool_calls_scores_zero_not_an_error():
    assert three([], REF) == (0.0, 0.0, 0.0)


def test_ragas_checks_the_references_arguments_and_tolerates_extra_actual_ones():
    ref = [tc("search_code", k=3)]
    with_query = traj(calls=[("search_code", {"query": "anything at all", "k": 3})])
    assert score_tool_calls_sync([(with_query, ref)]).accuracy == [1.0]  # extra `query` arg: fine
    wrong_k = traj(calls=[("search_code", {"query": "anything", "k": 9})])
    assert score_tool_calls_sync([(wrong_k, ref)]).accuracy == [0.0]  # wrong structured arg: caught


def test_a_reference_that_pins_free_text_penalises_a_good_paraphrase_unless_that_arg_is_ignored():
    ref = [tc("search_code", query="where is refresh_session", k=3)]
    reworded = traj(calls=[("search_code", {"query": "locate refresh_session", "k": 3})])
    assert score_tool_calls_sync([(reworded, ref)], ignore_args=()).accuracy == [0.5]  # args are scored proportionally: 1 of 2 matched
    assert score_tool_calls_sync([(reworded, ref)]).accuracy == [1.0]  # default: free-text `query` is not compared


def test_ragas_messages_carry_the_user_input_and_the_cleaned_calls():
    msgs = to_ragas_messages(traj(calls=[("search_code", {"query": "q", "k": 3})], report="ans", user_input="hello"))
    assert msgs[0].content == "hello" and msgs[1].content == "ans"
    assert [(c.name, c.args) for c in msgs[1].tool_calls] == [("search_code", {"k": 3})]


def test_the_deterministic_deepeval_path_never_touches_the_judge():
    judge = NoJudge()
    with pytest.raises(AssertionError, match="not deterministic"):
        judge.generate("prompt")
    assert judge.calls == 1  # ...and that is the only call: tool_correctness() asserts calls == 0 for itself
    tool_correctness([(traj(calls=["search_code"]), [tc("search_code")])])


# ---- on the real recorded Week 14 run ----


def test_on_a_single_hop_supervisor_all_three_tool_metrics_equal_handoff_accuracy():
    """The tool called is a pure function of the route, so tool-call metrics and handoff accuracy are the
    same number measured three independent ways -- a cross-check on the whole pipeline."""
    trajs = read_jsonl(RUNS / "w14_heuristic.jsonl")
    items = {i.id: i for i in load_routing()}
    pairs = [(t, items[t.id].reference_tool_calls) for t in trajs]
    ragas = score_tool_calls_sync(pairs)
    handoff = handoff_accuracy(routings_from(trajs)).accuracy
    assert ragas.mean_accuracy == pytest.approx(handoff)
    assert ragas.mean_f1 == pytest.approx(handoff)
    assert sum(tool_correctness(pairs)) / len(pairs) == pytest.approx(handoff)
