"""The Week 13 graph: receive query -> retrieve context -> generate answer, with memory.

State has two kinds of field, and the difference is the heart of LangGraph:

* ``messages`` is inherited from the prebuilt ``MessagesState``, which wires in the
  ``add_messages`` reducer: a node *returns* new messages and the framework *appends*
  them. This is the conversation history the checkpointer persists.
* ``question`` / ``context`` have no reducer: a node's return value *overwrites* them.
  They are per-turn scratch space, rebuilt on every turn.

Nodes are plain functions ``state -> partial state update``. Edges say what runs next.
``compile()`` validates the topology and returns a runnable; passing ``checkpointer=``
there is what makes state survive across ``invoke`` calls on the same ``thread_id``.
"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, MessagesState, StateGraph

from app.retrieval import BM25Retriever

SYSTEM_PROMPT = (
    "You are the Northwind API support assistant. Answer using the provided context and "
    "the earlier conversation. If neither contains the answer, say you don't know. "
    "Be concise -- one or two sentences."
)

TOP_K = 3


class State(MessagesState):
    # `messages` is inherited from MessagesState (list[AnyMessage] + add_messages reducer: append)
    question: str  # no reducer: overwritten each turn
    context: list[str]  # no reducer: overwritten each turn


def latest_user_text(messages: list[AnyMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return str(message.content)
    raise ValueError("no user message in state")


def build_graph(
    llm: BaseChatModel,
    retriever: BM25Retriever | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
    top_k: int = TOP_K,
):
    retriever = retriever or BM25Retriever()

    def receive_query(state: State) -> dict:
        return {"question": latest_user_text(state["messages"])}

    def retrieve_context(state: State) -> dict:
        docs = retriever.retrieve(state["question"], k=top_k)
        return {"context": [f"[{d.id}] {d.text}" for d in docs]}

    def generate_answer(state: State) -> dict:
        context_block = "\n\n".join(state["context"])
        system = SystemMessage(content=f"{SYSTEM_PROMPT}\n\nContext for this turn:\n{context_block}")
        reply = llm.invoke([system, *state["messages"]])
        return {"messages": [reply]}

    builder = StateGraph(State)
    builder.add_node("receive_query", receive_query)
    builder.add_node("retrieve_context", retrieve_context)
    builder.add_node("generate_answer", generate_answer)
    builder.add_edge(START, "receive_query")
    builder.add_edge("receive_query", "retrieve_context")
    builder.add_edge("retrieve_context", "generate_answer")
    builder.add_edge("generate_answer", END)
    return builder.compile(checkpointer=checkpointer)


def ask(graph, question: str, thread_id: str) -> AIMessage:
    """One conversational turn. Only the NEW message is passed in; the checkpointer
    restores everything before it for this thread_id."""
    result = graph.invoke(
        {"messages": [HumanMessage(content=question)]},
        config={"configurable": {"thread_id": thread_id}},
    )
    return result["messages"][-1]
