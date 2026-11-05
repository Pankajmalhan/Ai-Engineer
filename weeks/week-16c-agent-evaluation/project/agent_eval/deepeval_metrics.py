"""DeepEval's agent metrics: which can score a recorded run, which need a live trace, which need a judge.

Three layers (DeepEval's own taxonomy):
  action     ToolCorrectness (deterministic), ArgumentCorrectness (LLM)      -- one tool-calling decision
  reasoning  PlanQuality, PlanAdherence (LLM)                                -- the plan, and sticking to it
  execution  TaskCompletion, StepEfficiency (LLM)                            -- the whole path / the outcome

DeepEval documents the trajectory metrics (reasoning + execution) against a *trace* captured by ``@observe``.
The installed version (4.3.1) will also accept a plain ``LLMTestCase`` -- they reach the judge, tested in
``test_trajectory_metrics_also_accept_a_plain_test_case`` -- but then all they have is ``tools_called``.
``replay`` re-emits a recorded run as a trace: an agent span with one named tool span per recorded call and the
trace's input/output/tools_called set, i.e. the shape the metrics see on a live run, so a recording can be gated
in CI without re-running the agent.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")

from deepeval.models import DeepEvalBaseLLM  # noqa: E402
from deepeval.test_case import LLMTestCase  # noqa: E402
from deepeval.test_case import ToolCall as DeToolCall  # noqa: E402
from deepeval.tracing import observe, update_current_trace  # noqa: E402

from agent_eval.trajectory import ToolCall, Trajectory  # noqa: E402


class NoJudge(DeepEvalBaseLLM):
    """A judge that fails the moment it is used.

    DeepEval's metric constructors insist on a model even for the deterministic ToolCorrectness path.
    Passing this proves, by construction, that a score came from no LLM: ``calls`` stays 0.
    """

    def __init__(self) -> None:
        self.calls = 0

    def load_model(self):
        return self

    def generate(self, prompt: str, schema=None):
        self.calls += 1
        raise AssertionError("NoJudge was asked to judge -- this metric is not deterministic here")

    async def a_generate(self, prompt: str, schema=None):
        self.calls += 1
        raise AssertionError("NoJudge was asked to judge -- this metric is not deterministic here")

    def get_model_name(self) -> str:
        return "no-judge"


def _de_call(c: ToolCall) -> DeToolCall:
    return DeToolCall(name=c.name, input_parameters=c.args)


def to_llm_test_case(t: Trajectory, expected: list[ToolCall] | None = None) -> LLMTestCase:
    return LLMTestCase(
        input=t.user_input,
        actual_output=t.report,
        tools_called=[_de_call(c) for c in t.tool_calls],
        expected_tools=[_de_call(c) for c in expected] if expected is not None else None,
    )


def tool_correctness(
    pairs: list[tuple[Trajectory, list[ToolCall]]], *, threshold: float = 0.9, consider_ordering: bool = False
) -> list[float]:
    """Deterministic ToolCorrectness. Compares tool *names* (not arguments) unless told otherwise.

    Semantics worth knowing: extra calls are NOT penalised (every expected tool was called -> 1.0);
    with ``consider_ordering`` a swapped pair scores 0.5. Compare RAGAS ToolCallAccuracy, where an extra call is 0.0.
    """
    judge = NoJudge()
    scores = []
    for traj, expected in pairs:
        metric = ToolCorrectnessMetric(
            threshold=threshold, model=judge, async_mode=False, include_reason=False, verbose_mode=False,
            should_consider_ordering=consider_ordering,
        )
        metric.measure(to_llm_test_case(traj, expected))
        scores.append(metric.score)
    assert judge.calls == 0
    return scores


from deepeval.metrics import (  # noqa: E402
    ArgumentCorrectnessMetric,
    PlanAdherenceMetric,
    PlanQualityMetric,
    StepEfficiencyMetric,
    TaskCompletionMetric,
    ToolCorrectnessMetric,
)


@dataclass(frozen=True)
class Thresholds:
    """Gate levels. Judged metrics are noisy, so these are floors for a regression gate, not targets."""

    task_completion: float = 0.7
    step_efficiency: float = 0.5
    plan_quality: float = 0.7
    plan_adherence: float = 0.7
    tool_correctness: float = 0.9
    argument_correctness: float = 0.7


def build_trajectory_metrics(model: str | DeepEvalBaseLLM, th: Thresholds = Thresholds()) -> list:
    """The four trajectory metrics. All LLM-judged -- ``model`` is the judge (e.g. 'gpt-4o-mini')."""
    return [
        TaskCompletionMetric(threshold=th.task_completion, model=model),
        StepEfficiencyMetric(threshold=th.step_efficiency, model=model),
        PlanQualityMetric(threshold=th.plan_quality, model=model),
        PlanAdherenceMetric(threshold=th.plan_adherence, model=model),
    ]


def build_component_metrics(model: str | DeepEvalBaseLLM, th: Thresholds = Thresholds()) -> list:
    return [
        ToolCorrectnessMetric(threshold=th.tool_correctness, model=model),
        ArgumentCorrectnessMetric(threshold=th.argument_correctness, model=model),
    ]


# ---- replaying a recorded run as a DeepEval trace ----


def _tool_span(name: str):
    @observe(type="tool", name=name)
    def tool(arguments: dict):
        return "(recorded)"

    return tool


@observe(type="agent", name="replayed-agent")
def replay(t: Trajectory) -> str:
    """Re-emit a recorded run as a trace. Call it inside a test, then ``assert_test(golden=..., metrics=...)``.

    Limitation: sub-agent nesting is flattened -- every recorded tool call becomes a sibling tool span under
    the one agent span, so metrics see the order of calls but not which sub-agent made them.
    """
    for call in t.tool_calls:
        _tool_span(call.name)(call.args)
    update_current_trace(
        input=t.user_input,
        output=t.report,
        tools_called=[_de_call(c) for c in t.tool_calls],
    )
    return t.final_output
