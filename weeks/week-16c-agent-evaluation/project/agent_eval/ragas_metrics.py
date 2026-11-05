"""RAGAS's agentic metrics over recorded trajectories.

* ``ToolCallAccuracy`` -- strict: the actual calls must equal the reference calls, in order. One extra
  call, one wrong argument, or one call out of order -> 0.0.
* ``ToolCallF1`` -- unordered precision/recall over (name, args) calls: a gradient instead of a cliff.
  Both are deterministic -- no judge model, so they run in CI for free.
* ``AgentGoalAccuracyWithReference`` -- an LLM judge decides whether the conversation reached the
  reference goal. Needs a judge (OPENAI_API_KEY); not run by the offline suite.

RAGAS compares the *reference* call's arguments one by one against the actual call (extra actual arguments
are tolerated; each reference argument that differs costs a proportional share of the score). A reference
that pins a free-text argument (a search ``query``) therefore marks down any good paraphrase -- so by default free-text arguments are
dropped from both sides and only the *structured* ones (``k``) are checked. Whether the query text was any
good is a judgement call for an LLM metric (DeepEval's ArgumentCorrectness), not string equality.
"""

from __future__ import annotations

import asyncio
import warnings
from dataclasses import dataclass, field

from agent_eval.trajectory import ToolCall, Trajectory

FREE_TEXT_ARGS = ("query",)


def _strip(call: ToolCall, ignore: tuple[str, ...]) -> dict:
    return {k: v for k, v in call.args.items() if k not in ignore}


def to_ragas_messages(t: Trajectory, ignore_args: tuple[str, ...] = FREE_TEXT_ARGS) -> list:
    from ragas.messages import AIMessage, HumanMessage
    from ragas.messages import ToolCall as RagasToolCall

    calls = [RagasToolCall(name=c.name, args=_strip(c, ignore_args)) for c in t.tool_calls]
    return [HumanMessage(content=t.user_input), AIMessage(content=t.final_output, tool_calls=calls)]


def _reference(calls: list[ToolCall], ignore: tuple[str, ...]) -> list:
    from ragas.messages import ToolCall as RagasToolCall

    return [RagasToolCall(name=c.name, args=_strip(c, ignore)) for c in calls]


@dataclass
class ToolCallScores:
    ids: list[str] = field(default_factory=list)
    accuracy: list[float] = field(default_factory=list)
    f1: list[float] = field(default_factory=list)

    @property
    def mean_accuracy(self) -> float:
        return sum(self.accuracy) / len(self.accuracy)

    @property
    def mean_f1(self) -> float:
        return sum(self.f1) / len(self.f1)


async def score_tool_calls(
    pairs: list[tuple[Trajectory, list[ToolCall]]], ignore_args: tuple[str, ...] = FREE_TEXT_ARGS
) -> ToolCallScores:
    """``pairs`` = (what the agent did, what it should have called)."""
    from ragas.metrics.collections import ToolCallAccuracy, ToolCallF1

    accuracy, f1 = ToolCallAccuracy(), ToolCallF1()
    scores = ToolCallScores()
    with warnings.catch_warnings():
        # RAGAS warns on length mismatches and empty traces; the scores already say so.
        warnings.simplefilter("ignore", UserWarning)
        for traj, reference in pairs:
            messages, ref = to_ragas_messages(traj, ignore_args), _reference(reference, ignore_args)
            scores.ids.append(traj.id)
            scores.accuracy.append((await accuracy.ascore(user_input=messages, reference_tool_calls=ref)).value)
            scores.f1.append((await f1.ascore(user_input=messages, reference_tool_calls=ref)).value)
    return scores


def score_tool_calls_sync(pairs, ignore_args: tuple[str, ...] = FREE_TEXT_ARGS) -> ToolCallScores:
    return asyncio.run(score_tool_calls(pairs, ignore_args))


def build_ragas_judge(model: str = "gpt-4o-mini"):
    """The judge for AgentGoalAccuracy. Needs OPENAI_API_KEY."""
    from openai import AsyncOpenAI
    from ragas.llms import llm_factory

    return llm_factory(model, client=AsyncOpenAI())


async def score_goal_accuracy(pairs: list[tuple[Trajectory, str]], llm) -> list[float]:
    """``pairs`` = (trajectory, reference goal). LLM-judged, 1.0 = reached the goal. NOT run offline."""
    from ragas.metrics.collections import AgentGoalAccuracyWithReference

    metric = AgentGoalAccuracyWithReference(llm=llm)
    return [(await metric.ascore(user_input=to_ragas_messages(t), reference=goal)).value for t, goal in pairs]
