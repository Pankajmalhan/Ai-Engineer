import pytest

from app.graph import ask, build_graph, resume
from tests.conftest import CountingRetriever, ScriptedClassifier, route

THREAD = "t1"


def make(classifier, checkpointer, **kwargs):
    return build_graph(classifier, checkpointer=checkpointer, **kwargs)


@pytest.mark.parametrize("category", ["code", "rules", "domain"])
def test_confident_query_goes_to_matching_agent_without_interrupt(checkpointer, category):
    clf = ScriptedClassifier({}, default=route(category, 0.9))
    turn = ask(make(clf, checkpointer), "anything", THREAD)
    assert not turn.interrupted
    assert turn.agent == f"{category}_agent"
    assert turn.hits and turn.hits[0]["source"].startswith(f"{category}-stub")
    assert f"[{category}_agent]" in turn.answer


def test_only_the_chosen_agents_retriever_runs(checkpointer):
    spies = {c: CountingRetriever(c) for c in ("code", "rules", "domain")}
    clf = ScriptedClassifier({}, default=route("rules", 0.9))
    ask(make(clf, checkpointer, retrievers=spies), "q", THREAD)
    assert len(spies["rules"].calls) == 1
    assert spies["code"].calls == [] and spies["domain"].calls == []


def test_low_confidence_pauses_graph_before_any_agent_runs(checkpointer):
    spy = CountingRetriever("code")
    graph = make(ScriptedClassifier({}, default=route("code", 0.4)), checkpointer, retrievers={"code": spy})
    turn = ask(graph, "vague", THREAD)

    assert turn.interrupted
    assert turn.interrupt["type"] == "clarification"
    assert turn.interrupt["guess"] == "code"
    assert turn.interrupt["options"] == ["code", "rules", "domain"]
    assert spy.calls == []  # nothing ran yet
    # the pause is a real checkpoint: the graph says exactly which node is waiting
    assert graph.get_state({"configurable": {"thread_id": THREAD}}).next == ("clarify",)


def test_threshold_is_strict_less_than(checkpointer):
    clf = ScriptedClassifier({}, default=route("code", 0.6))
    assert not ask(make(clf, checkpointer, threshold=0.6), "q", THREAD).interrupted


def test_resume_with_category_routes_directly_and_skips_reclassification(checkpointer):
    clf = ScriptedClassifier({}, default=route("code", 0.3))
    graph = make(clf, checkpointer)
    ask(graph, "vague", THREAD)
    assert len(clf.calls) == 1

    turn = resume(graph, "domain", THREAD)
    assert not turn.interrupted
    assert turn.agent == "domain_agent"
    assert turn.route["reasoning"] == "chosen by human"
    # the human's answer replaced the LLM call: resuming did not re-run the classifier
    assert len(clf.calls) == 1


def test_resume_with_free_text_reclassifies_with_the_added_detail(checkpointer):
    clf = ScriptedClassifier(
        {"clarification: the python file": route("code", 0.9)},
        default=route("domain", 0.3),
    )
    graph = make(clf, checkpointer)
    assert ask(graph, "session thing", THREAD).interrupted

    turn = resume(graph, "the python file", THREAD)
    assert turn.agent == "code_agent"
    assert "session thing" in clf.calls[-1] and "the python file" in clf.calls[-1]
    assert len(clf.calls) == 2


def test_clarification_loop_is_bounded(checkpointer):
    # classifier is *always* unsure; after max_clarifications the graph must stop asking
    clf = ScriptedClassifier({}, default=route("rules", 0.2))
    graph = make(clf, checkpointer, max_clarifications=1)
    assert ask(graph, "q", THREAD).interrupted
    turn = resume(graph, "still vague, no category here", THREAD)
    assert not turn.interrupted
    assert turn.agent == "rules_agent"  # fell back to the best guess
    assert len(clf.calls) == 2


def test_clarification_is_recorded_in_message_history(checkpointer):
    graph = make(ScriptedClassifier({}, default=route("code", 0.3)), checkpointer)
    ask(graph, "vague", THREAD)
    resume(graph, "code", THREAD)
    roles = [m.type for m in graph.get_state({"configurable": {"thread_id": THREAD}}).values["messages"]]
    assert roles == ["human", "ai", "human", "ai"]  # question, bot's clarifying q, human reply, answer


def test_approval_gate_pauses_before_the_tool_call_and_approve_runs_it(checkpointer):
    spy = CountingRetriever("code")
    graph = make(ScriptedClassifier({}, default=route("code", 0.9)), checkpointer,
                 retrievers={"code": spy}, require_approval=True)
    turn = ask(graph, "find it", THREAD)

    assert turn.interrupted and turn.interrupt["type"] == "approve_tool_call"
    assert turn.interrupt["agent"] == "code_agent"
    assert turn.interrupt["tool"] == "code_retriever"
    assert turn.interrupt["args"]["query"] == "find it"
    assert spy.calls == []  # paused BEFORE the call

    done = resume(graph, True, THREAD)
    assert len(spy.calls) == 1 and done.hits


def test_approval_gate_reject_never_calls_the_tool(checkpointer):
    spy = CountingRetriever("rules")
    graph = make(ScriptedClassifier({}, default=route("rules", 0.9)), checkpointer,
                 retrievers={"rules": spy}, require_approval=True)
    ask(graph, "q", THREAD)
    done = resume(graph, False, THREAD)
    assert spy.calls == []
    assert done.hits == [] and "rejected" in done.answer


def test_clarify_then_approve_chains_two_interrupts_on_one_thread(checkpointer):
    spy = CountingRetriever("domain")
    graph = make(ScriptedClassifier({}, default=route("code", 0.3)), checkpointer,
                 retrievers={"domain": spy}, require_approval=True)
    assert ask(graph, "q", THREAD).interrupt["type"] == "clarification"
    assert resume(graph, "domain", THREAD).interrupt["type"] == "approve_tool_call"
    assert resume(graph, True, THREAD).agent == "domain_agent"
    assert len(spy.calls) == 1


def test_second_turn_on_same_thread_starts_with_fresh_routing_state(checkpointer):
    clf = ScriptedClassifier({"first": route("code", 0.9), "second": route("rules", 0.9)})
    graph = make(clf, checkpointer)
    assert ask(graph, "first", THREAD).agent == "code_agent"
    turn = ask(graph, "second", THREAD)
    assert turn.agent == "rules_agent"
    assert clf.calls == ["first", "second"]  # no stale clarification text leaked into turn 2


def test_different_threads_pause_independently(checkpointer):
    graph = make(ScriptedClassifier({}, default=route("code", 0.3)), checkpointer)
    assert ask(graph, "a", "A").interrupted
    assert ask(graph, "b", "B").interrupted
    assert resume(graph, "code", "A").agent == "code_agent"
    # B is still waiting
    assert graph.get_state({"configurable": {"thread_id": "B"}}).next == ("clarify",)
