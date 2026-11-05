"""The Week 14 graph: a supervisor that routes to one of three sub-agents, with human-in-the-loop.

                      +--> code_agent ----+
    receive_query --> supervisor --> rules_agent ---+--> END
                      |   ^         +--> domain_agent -+
                      v   |
                     clarify   (interrupt: pauses the graph and asks the human)

Routing uses ``Command(goto=..., update=...)``: a node returns *both* its state update and the
name of the next node, so the supervisor needs no separate conditional-edge function. Nodes that
return ``Command`` must NOT also have static outgoing edges (both would fire) -- so the supervisor,
clarify and the agents' fan-out are wired only through ``Command``; only ``receive_query -> supervisor``
and ``<agent> -> END`` are static edges.

Two interrupts, one mechanism (``interrupt()`` + a checkpointer + ``Command(resume=...)``):

1. ``clarify`` -- confidence below the threshold: ask the human which specialist is right.
2. the agents' optional approval gate (``require_approval=True``) -- pause *before* the retrieval
   "tool call" and let the human approve or reject it.

Key fact about ``interrupt()``: on resume the *whole node restarts from its first line*, and the
resume value becomes ``interrupt()``'s return value. So anything before the interrupt must be
cheap and idempotent. That is why classification (an LLM call) lives in ``supervisor`` and the
interrupt lives in its own tiny ``clarify`` node -- resuming re-runs ``clarify``, not the LLM call.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.types import Command, interrupt

from app.classifiers import Classifier
from app.retrievers import Retriever, lookup_rules, search_code, search_domain_docs
from app.schemas import CATEGORIES, CONFIDENCE_THRESHOLD, Route

TOP_K = 3
MAX_CLARIFICATIONS = 1  # after this many questions, stop asking and use the best guess

AgentName = Literal["code_agent", "rules_agent", "domain_agent"]


class State(MessagesState):
    # `messages` (inherited): conversation history, append-only via the add_messages reducer.
    query: str  # the text being routed; grows when the human clarifies. Overwritten each turn.
    route: dict  # latest Route as a dict (JSON-serialisable so checkpoints can store it)
    clarifications: int  # how many times we've interrupted this turn
    agent: str  # which sub-agent produced the answer
    hits: list[dict]  # what that agent retrieved


def latest_user_text(messages: list[AnyMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return str(message.content)
    raise ValueError("no user message in state")


def default_retrievers() -> dict[str, Retriever]:
    return {"code": search_code, "rules": lookup_rules, "domain": search_domain_docs}


def build_graph(
    classifier: Classifier,
    retrievers: dict[str, Retriever] | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
    threshold: float = CONFIDENCE_THRESHOLD,
    max_clarifications: int = MAX_CLARIFICATIONS,
    require_approval: bool = False,
    top_k: int = TOP_K,
):
    """``checkpointer`` is required for any interrupt to work -- the pause is a saved checkpoint."""
    retrievers = {**default_retrievers(), **(retrievers or {})}

    def receive_query(state: State) -> dict:
        # Reset per-turn scratch space so a long thread doesn't leak the previous turn's routing.
        return {"query": latest_user_text(state["messages"]), "clarifications": 0, "route": {}, "hits": []}

    def supervisor(state: State) -> Command[Literal["code_agent", "rules_agent", "domain_agent", "clarify"]]:
        route = classifier.classify(state["query"])
        uncertain = route.confidence < threshold and state["clarifications"] < max_clarifications
        goto = "clarify" if uncertain else f"{route.category}_agent"
        return Command(update={"route": route.model_dump()}, goto=goto)

    def clarify(state: State) -> Command[Literal["supervisor", "code_agent", "rules_agent", "domain_agent"]]:
        route = state["route"]
        # Everything before this line re-runs on resume; there is nothing expensive above it.
        answer = interrupt(
            {
                "type": "clarification",
                "question": (
                    f"I'm not sure how to route this (best guess: {route['category']}, "
                    f"confidence {route['confidence']:.2f}). Is it about code, rules, or domain docs? "
                    "Pick one, or add detail."
                ),
                "guess": route["category"],
                "confidence": route["confidence"],
                "options": list(CATEGORIES),
            }
        )
        answer = str(answer).strip()
        history = [AIMessage(content="Which area is this about: code, rules, or domain docs?"), HumanMessage(content=answer)]
        if answer.lower() in CATEGORIES:
            # The human picked the specialist outright: trust them, skip re-classifying.
            chosen = Route(category=answer.lower(), confidence=1.0, reasoning="chosen by human")
            return Command(update={"route": chosen.model_dump(), "messages": history}, goto=f"{chosen.category}_agent")
        # Free-text detail: fold it into the query and let the supervisor try again.
        return Command(
            update={
                "query": f"{state['query']}\n(clarification: {answer})",
                "clarifications": state["clarifications"] + 1,
                "messages": history,
            },
            goto="supervisor",
        )

    def make_agent(category: str, name: str):
        retrieve = retrievers[category]

        def agent(state: State) -> dict:
            if require_approval:
                # Pause BEFORE the tool call. Nothing has been retrieved yet, so a "no" costs nothing.
                approved = interrupt(
                    {
                        "type": "approve_tool_call",
                        "agent": name,
                        "tool": getattr(retrieve, "__name__", category),
                        "args": {"query": state["query"], "k": top_k},
                    }
                )
                if not approved:
                    return {
                        "agent": name,
                        "hits": [],
                        "messages": [AIMessage(content=f"[{name}] retrieval was rejected by the user.", name=name)],
                    }
            hits = retrieve(state["query"], top_k)
            body = "\n".join(f"- ({h.source}) {h.text}" for h in hits)
            return {
                "agent": name,
                "hits": [h.model_dump() for h in hits],
                "messages": [AIMessage(content=f"[{name}] top results:\n{body}", name=name)],
            }

        return agent

    builder = StateGraph(State)
    builder.add_node("receive_query", receive_query)
    builder.add_node("supervisor", supervisor)
    builder.add_node("clarify", clarify)
    builder.add_edge(START, "receive_query")
    builder.add_edge("receive_query", "supervisor")
    for category in CATEGORIES:
        name = f"{category}_agent"
        builder.add_node(name, make_agent(category, name))
        builder.add_edge(name, END)
    return builder.compile(checkpointer=checkpointer)


# ---- thin driver helpers -------------------------------------------------------------------


@dataclass
class TurnResult:
    """What a caller needs after one ``invoke``: either an answer, or a question for the human."""

    interrupt: dict | None = None
    agent: str | None = None
    route: dict = field(default_factory=dict)
    hits: list[dict] = field(default_factory=list)
    answer: str | None = None

    @property
    def interrupted(self) -> bool:
        return self.interrupt is not None


def _to_result(raw: dict[str, Any]) -> TurnResult:
    pending = raw.get("__interrupt__")
    if pending:
        return TurnResult(interrupt=pending[0].value, route=raw.get("route", {}))
    return TurnResult(
        agent=raw.get("agent"),
        route=raw.get("route", {}),
        hits=raw.get("hits", []),
        answer=str(raw["messages"][-1].content),
    )


def ask(graph, question: str, thread_id: str) -> TurnResult:
    config = {"configurable": {"thread_id": thread_id}}
    return _to_result(graph.invoke({"messages": [HumanMessage(content=question)]}, config=config))


def resume(graph, value: Any, thread_id: str) -> TurnResult:
    """Answer the pending interrupt on this thread. ``value`` becomes ``interrupt()``'s return."""
    config = {"configurable": {"thread_id": thread_id}}
    return _to_result(graph.invoke(Command(resume=value), config=config))
