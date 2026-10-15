from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from app.graph import ask, build_graph, latest_user_text


def test_graph_has_exactly_the_three_nodes_in_order(fake_llm):
    graph = build_graph(fake_llm)
    drawn = graph.get_graph()
    assert {n for n in drawn.nodes} == {
        "__start__", "receive_query", "retrieve_context", "generate_answer", "__end__",
    }
    edges = {(e.source, e.target) for e in drawn.edges}
    assert edges == {
        ("__start__", "receive_query"),
        ("receive_query", "retrieve_context"),
        ("retrieve_context", "generate_answer"),
        ("generate_answer", "__end__"),
    }


def test_single_turn_populates_state_and_answers_from_retrieved_context(fake_llm):
    graph = build_graph(fake_llm)
    out = graph.invoke({"messages": [HumanMessage(content="What is the rate limit on the Pro tier?")]})
    assert out["question"] == "What is the rate limit on the Pro tier?"
    assert out["context"][0].startswith("[rate-limits]")
    assert len(out["context"]) == 3
    assert "600 requests per minute" in out["messages"][-1].content


def test_generate_prompt_contains_context_but_history_does_not(fake_llm):
    graph = build_graph(fake_llm, checkpointer=MemorySaver())
    ask(graph, "How do refunds work?", "t1")
    ask(graph, "What is the rate limit on the Pro tier?", "t1")
    second_prompt = fake_llm.calls[1]
    assert "[rate-limits]" in second_prompt[0].content
    # the first turn's retrieved docs were scratch space, not history
    assert "[refunds]" not in second_prompt[0].content
    assert [type(m).__name__ for m in second_prompt[1:]] == ["HumanMessage", "AIMessage", "HumanMessage"]


def test_without_checkpointer_each_call_forgets(fake_llm):
    graph = build_graph(fake_llm)
    graph.invoke({"messages": [HumanMessage(content="What is the rate limit on the Pro tier?")]})
    out = graph.invoke({"messages": [HumanMessage(content="Repeat the number from your first answer.")]})
    assert len(out["messages"]) == 2  # just this call's human + ai
    assert out["messages"][-1].content == "I don't know."


def test_memory_saver_carries_history_across_turns(fake_llm):
    graph = build_graph(fake_llm, checkpointer=MemorySaver())
    first = ask(graph, "What is the rate limit on the Pro tier?", "t1")
    assert "600 requests per minute" in first.content

    follow_up = ask(graph, "Repeat the number from your first answer.", "t1")
    # the model could only say this because turn 1's answer was in the prompt it received
    assert follow_up.content == f"Earlier I said: {first.content}"
    roles = [type(m).__name__ for m in graph.get_state({"configurable": {"thread_id": "t1"}}).values["messages"]]
    assert roles == ["HumanMessage", "AIMessage", "HumanMessage", "AIMessage"]


def test_threads_are_isolated(fake_llm):
    graph = build_graph(fake_llm, checkpointer=MemorySaver())
    ask(graph, "What is the rate limit on the Pro tier?", "alice")
    reply = ask(graph, "Repeat the number from your first answer.", "bob")
    assert reply.content == "I don't know."
    bob = graph.get_state({"configurable": {"thread_id": "bob"}}).values["messages"]
    assert len(bob) == 2


def test_context_is_overwritten_not_accumulated(fake_llm):
    graph = build_graph(fake_llm, checkpointer=MemorySaver())
    ask(graph, "How do refunds work?", "t1")
    ask(graph, "What is the rate limit on the Pro tier?", "t1")
    state = graph.get_state({"configurable": {"thread_id": "t1"}}).values
    assert len(state["context"]) == 3  # replaced, not 6
    assert state["question"] == "What is the rate limit on the Pro tier?"
    assert len(state["messages"]) == 4  # appended by the add_messages reducer


def test_checkpoint_history_has_one_checkpoint_per_step(fake_llm):
    graph = build_graph(fake_llm, checkpointer=MemorySaver())
    ask(graph, "How do refunds work?", "t1")
    history = list(graph.get_state_history({"configurable": {"thread_id": "t1"}}))
    # input, after receive_query, after retrieve_context, after generate_answer (+ initial empty)
    assert history[0].next == ()
    assert ("generate_answer",) in [h.next for h in history]
    assert ("retrieve_context",) in [h.next for h in history]


def test_token_usage_is_kept_on_the_ai_message(fake_llm):
    graph = build_graph(fake_llm)
    out = graph.invoke({"messages": [HumanMessage(content="How do refunds work?")]})
    ai = out["messages"][-1]
    assert isinstance(ai, AIMessage)
    assert ai.usage_metadata["total_tokens"] == 15


def test_latest_user_text_picks_the_last_human_message():
    msgs = [HumanMessage(content="a"), AIMessage(content="b"), HumanMessage(content="c")]
    assert latest_user_text(msgs) == "c"
