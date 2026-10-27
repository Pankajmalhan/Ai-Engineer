"""DeepEval agent metrics: construction, thresholds, and replaying a recorded run as a real trace."""

from deepeval.tracing import observe
from deepeval.tracing.context import current_trace_context

from agent_eval.deepeval_metrics import NoJudge, Thresholds, build_component_metrics, build_trajectory_metrics, replay
from tests.conftest import traj


def capture(t):
    """Run replay() under an outer span so the finished trace is still reachable afterwards."""
    box = {}

    @observe(type="agent", name="outer")
    def outer(recorded):
        replay(recorded)
        box["trace"] = current_trace_context.get()

    outer(t)
    return box["trace"]


def spans(trace):
    outer = trace.root_spans[0]
    replayed = outer.children[0]
    return replayed, replayed.children


def test_replay_emits_one_named_tool_span_per_recorded_call_in_order():
    t = traj(report="final", calls=[("search_code", {"q": 1}), ("read_code", {"path": "p"}), ("search_code", {"q": 2})], user_input="the question")
    replayed, children = spans(capture(t))
    assert replayed.name == "replayed-agent"
    assert [c.name for c in children] == ["search_code", "read_code", "search_code"]
    assert all(type(c).__name__ == "ToolSpan" for c in children)


def test_replay_sets_the_trace_input_output_and_tools_called():
    t = traj(report="the answer", calls=[("lookup_rules", {"k": 3})], user_input="the question")
    trace = capture(t)
    assert trace.input == "the question" and trace.output == "the answer"
    assert [(c.name, c.input_parameters) for c in trace.tools_called] == [("lookup_rules", {"k": 3})]


def test_replay_of_a_run_that_saved_a_file_reports_the_file_content():
    trace = capture(traj(report="saved.", files={"/audit.md": "THE AUDIT"}))
    assert "THE AUDIT" in trace.output


def test_the_four_trajectory_metrics_and_two_component_metrics_are_built_with_the_gate_thresholds():
    th = Thresholds(task_completion=0.8, step_efficiency=0.6, plan_quality=0.75, plan_adherence=0.65, tool_correctness=0.95, argument_correctness=0.7)
    judge = NoJudge()
    trajectory = build_trajectory_metrics(judge, th)
    component = build_component_metrics(judge, th)
    assert [type(m).__name__ for m in trajectory] == ["TaskCompletionMetric", "StepEfficiencyMetric", "PlanQualityMetric", "PlanAdherenceMetric"]
    assert [m.threshold for m in trajectory] == [0.8, 0.6, 0.75, 0.65]
    assert [type(m).__name__ for m in component] == ["ToolCorrectnessMetric", "ArgumentCorrectnessMetric"]
    assert [m.threshold for m in component] == [0.95, 0.7]
    assert judge.calls == 0  # building metrics costs nothing


def test_the_llm_test_case_judges_the_deliverable_not_just_the_confirmation_message():
    from agent_eval.deepeval_metrics import to_llm_test_case

    case = to_llm_test_case(traj(report="saved.", files={"/audit.md": "THE AUDIT"}))
    assert "THE AUDIT" in case.actual_output


def test_trajectory_metrics_also_accept_a_plain_test_case():
    """They are documented against traces, but 4.3.1 lets a plain LLMTestCase through to the judge (so
    replay is about giving them the richer span shape, not about being able to run them at all)."""
    from agent_eval.deepeval_metrics import to_llm_test_case

    judge = NoJudge()
    metrics = build_trajectory_metrics(judge)
    for m in metrics:
        m.async_mode = False
        try:
            m.measure(to_llm_test_case(traj(report="a", calls=["search_code"])))
        except AssertionError:
            pass  # NoJudge refuses -- which proves the metric got as far as asking a judge
    assert judge.calls == len(metrics)
