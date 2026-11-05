"""The Week 14 pattern, looped: hop limits, what reaches the writer, planner wiring."""

import pytest
from langchain_core.messages import AIMessage, SystemMessage
from pydantic import ValidationError

from app.offline import ScriptedPlanner, default_planner, oracle_writer
from app.runners import run_supervisor
from app.supervisor import SUPERVISOR_PROMPT, WRITER_PROMPT, LLMPlanner, Step, build_supervisor_graph, initial_state
from app.task import TASK


def run(planner, *, max_hops):
    writer = oracle_writer()
    graph = build_supervisor_graph(planner, writer, max_hops=max_hops)
    return graph.invoke(initial_state(TASK)), writer


def test_loop_visits_each_specialist_once_then_writes():
    out, _ = run(default_planner(), max_hops=6)
    assert out["trail"] == ["code", "rules", "domain"]
    assert out["hops"] == 3


def test_one_hop_reproduces_week_14_route_once_then_answer():
    planner = default_planner()
    out, _ = run(planner, max_hops=1)
    assert out["trail"] == ["code"]
    assert planner.calls == 1  # the planner is not even asked a second time


def test_a_planner_that_never_finishes_is_stopped_by_the_hop_cap():
    stubborn = ScriptedPlanner([Step(next="code", query="session")])  # repeats forever
    out, _ = run(stubborn, max_hops=4)
    assert out["trail"] == ["code"] * 4
    assert isinstance(out["messages"][-1], AIMessage)  # still got a report out


def test_specialists_search_with_the_query_the_planner_chose():
    planner = ScriptedPlanner([Step(next="code", query="invoice generation"), Step(next="finish")])
    out, _ = run(planner, max_hops=3)
    evidence = next(m for m in out["messages"] if getattr(m, "name", None) == "code_agent")
    assert "generate_invoices" in evidence.content  # billing code, not session code
    assert "full file: code/src/billing/invoices.py" in evidence.content


def test_all_gathered_evidence_is_in_the_one_shared_thread_the_writer_sees():
    _, writer = run(default_planner(), max_hops=6)
    prompt = writer.prompts[-1]
    assert prompt[0] == SystemMessage(WRITER_PROMPT)
    seen = {m.name for m in prompt if isinstance(m, AIMessage) and m.name}
    assert seen == {"code_agent", "rules_agent", "domain_agent"}
    # the whole file the code specialist opened is sitting in the shared context, raw
    assert any("Session management for the web app" in str(m.content) for m in prompt)


def test_the_loop_gets_the_full_score_and_one_hop_cannot():
    full = run_supervisor("loop", default_planner(), oracle_writer(), max_hops=6)
    one = run_supervisor("one", default_planner(), oracle_writer(), max_hops=1)
    assert full.error is None and full.score.points == 6
    assert one.score.points == 1 and "max_lifetime" in one.score.missing
    assert full.metrics.tool_calls == {"code_agent": 1, "rules_agent": 1, "domain_agent": 1}


def test_step_rejects_an_unknown_specialist():
    with pytest.raises(ValidationError):
        Step(next="billing", query="x")


def test_llm_planner_asks_for_structured_output_and_prepends_the_supervisor_prompt():
    class FakeChain:
        seen = None

        def invoke(self, messages):
            FakeChain.seen = messages
            return Step(next="finish")

    class FakeLLM:
        schema = None

        def with_structured_output(self, schema):
            FakeLLM.schema = schema
            return FakeChain()

    state = initial_state("do the audit")
    step = LLMPlanner(FakeLLM()).next_step(state["messages"])
    assert FakeLLM.schema is Step and step.next == "finish"
    assert FakeChain.seen[0] == SystemMessage(SUPERVISOR_PROMPT)
    assert FakeChain.seen[1].content == "do the audit"
