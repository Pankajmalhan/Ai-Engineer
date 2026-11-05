"""The LLM-judged agent gates -- the part that needs OPENAI_API_KEY *and* recorded real-model runs.

Same gate-on-regression pattern as Week 6, now for trajectories: each recorded run is replayed as a trace and
must clear DeepEval's trajectory metrics; the Week 14 run must clear RAGAS AgentGoalAccuracy. Both skip with an
explicit reason until there is something real to judge:

    uv run python scripts/record.py w16b --trials 3     # needs OPENAI_API_KEY; writes data/runs/w16b_tasks_10.jsonl
    uv run python scripts/record.py w14 --classifier llm
    uv run pytest tests/test_agent_gates.py -v

NOTE: written against the DeepEval and RAGAS docs/signatures; never executed with a live judge.
"""

import asyncio

import pytest
from deepeval import assert_test
from deepeval.dataset import Golden
from deepeval.test_case import ToolCall as DeToolCall

from agent_eval.datasets import RUNS, load_routing
from agent_eval.deepeval_metrics import Thresholds, build_component_metrics, build_trajectory_metrics, replay, to_llm_test_case
from agent_eval.trajectory import read_jsonl
from tests.conftest import requires_openai

JUDGE = "gpt-4o-mini"
W16B_REAL = RUNS / "w16b_tasks_10.jsonl"
W14_LLM = RUNS / "w14_llm.jsonl"


def _w16b_params():
    if not W16B_REAL.exists():
        return [pytest.param(None, id="no-recorded-real-runs", marks=pytest.mark.skip(reason=f"{W16B_REAL.name} not recorded -- run scripts/record.py w16b"))]
    return [pytest.param(t, id=f"{t.id}-{t.meta['arch']}-{t.meta.get('trial', 0)}") for t in read_jsonl(W16B_REAL)]


@requires_openai
@pytest.mark.parametrize("trajectory", _w16b_params())
def test_trajectory_metrics_gate(trajectory):
    golden = Golden(input=trajectory.user_input)
    replay(trajectory)
    assert_test(golden=golden, metrics=build_trajectory_metrics(JUDGE, Thresholds()))


@requires_openai
@pytest.mark.parametrize("trajectory", _w16b_params())
def test_argument_correctness_gate(trajectory):
    from deepeval.metrics import ArgumentCorrectnessMetric

    assert_test(test_case=to_llm_test_case(trajectory), metrics=[ArgumentCorrectnessMetric(threshold=Thresholds().argument_correctness, model=JUDGE)])


@requires_openai
@pytest.mark.skipif(not W14_LLM.exists(), reason=f"{W14_LLM.name} not recorded -- run scripts/record.py w14 --classifier llm")
def test_ragas_agent_goal_accuracy_gate_on_the_llm_supervisor():
    from agent_eval.ragas_metrics import build_ragas_judge, score_goal_accuracy

    items = {i.id: i for i in load_routing()}
    trajs = read_jsonl(W14_LLM)
    scores = asyncio.run(score_goal_accuracy([(t, items[t.id].reference) for t in trajs], build_ragas_judge(JUDGE)))
    assert sum(scores) / len(scores) >= 0.7
