"""The Week 14 supervisor pattern, extended just enough to attempt a multi-step task.

                    +--> code_agent ---+
    START --> supervisor --> rules_agent --+--> (back to supervisor)
                |           +--> domain_agent +
                v
              writer --> END

Week 14's graph routed a query to ONE sub-agent and stopped (``max_hops=1`` reproduces that).
For a task that needs code + rules + policy, the minimum hand-rolled change is a loop: after each
specialist the supervisor looks again and either picks another specialist or says ``finish``.
Everything the harness gives you for free is visible here as something you wrote or lack:

* planning        -> the supervisor re-derives "what is left?" from the raw thread every hop
* context hygiene -> every specialist's raw output is appended to the one shared thread
* delegation      -> specialists are fixed functions, not agents that can reason over their results
* scratch space   -> none; the thread is the only memory
"""

from __future__ import annotations

from typing import Literal, Protocol

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.types import Command
from pydantic import BaseModel, Field

from app import corpus

Next = Literal["code", "rules", "domain", "finish"]

SUPERVISOR_PROMPT = """You supervise three specialists for a codebase audit:
- code: keyword search over the source, then reads the best-matching file
- rules: returns the team's coding rules (with ids)
- domain: keyword search over the domain docs (policies, glossary)
Look at the task and the evidence gathered so far. Pick the ONE specialist that should run next and
give it a short search query, or answer `finish` once the evidence covers every part of the task.
Do not repeat a specialist whose evidence is already in the thread."""

WRITER_PROMPT = """Write the final audit report in markdown, using only the evidence in the thread.
Sections: Location, Rule violations (cite rule ids), Policy mismatches (quote both values)."""


class Step(BaseModel):
    """What the supervisor must return each hop. Pydantic rejects an unknown specialist name."""

    next: Next = Field(description="Which specialist runs next, or `finish` to write the report.")
    query: str = Field(default="", description="Search query for that specialist.")
    reasoning: str = Field(default="", description="One short sentence.")


class Planner(Protocol):
    """The seam for the supervisor's brain: a real LLM in production, a script in tests."""

    def next_step(self, messages: list[BaseMessage]) -> Step: ...


class LLMPlanner:
    def __init__(self, llm: BaseChatModel):
        self._chain = llm.with_structured_output(Step)

    def next_step(self, messages: list[BaseMessage]) -> Step:
        return self._chain.invoke([SystemMessage(SUPERVISOR_PROMPT), *messages])


class State(MessagesState):
    query: str  # what the supervisor asked the current specialist to search for
    hops: int  # specialists run so far
    trail: list[str]  # which specialists ran, in order


def retrieve(category: str, query: str) -> str:
    """The three specialists. Plain functions, like Week 14's stubs -- but over a real corpus."""
    if category == "rules":
        return corpus.format_chunks(corpus.all_rules())
    chunks = corpus.search(category, query, k=3)
    body = corpus.format_chunks(chunks)
    if category == "code" and chunks:
        top = chunks[0].path  # an engineer would open the best hit, so the specialist does too
        body += f"\n\n=== full file: {top}\n{corpus.read(top)}"
    return body


def build_supervisor_graph(planner: Planner, writer: BaseChatModel, *, max_hops: int = 6):
    def supervisor(state: State) -> Command[Literal["code_agent", "rules_agent", "domain_agent", "writer"]]:
        if state["hops"] >= max_hops:
            return Command(goto="writer")
        step = planner.next_step(state["messages"])
        if step.next == "finish":
            return Command(goto="writer")
        return Command(goto=f"{step.next}_agent", update={"query": step.query})

    def make_specialist(category: str):
        name = f"{category}_agent"

        def specialist(state: State) -> Command[Literal["supervisor"]]:
            evidence = retrieve(category, state["query"])
            return Command(
                goto="supervisor",
                update={
                    "messages": [AIMessage(content=f"[{name}] results for {state['query']!r}:\n{evidence}", name=name)],
                    "hops": state["hops"] + 1,
                    "trail": [*state["trail"], category],
                },
            )

        return name, specialist

    def write_report(state: State) -> dict:
        return {"messages": [writer.invoke([SystemMessage(WRITER_PROMPT), *state["messages"]])]}

    builder = StateGraph(State)
    builder.add_node("supervisor", supervisor)
    builder.add_node("writer", write_report)
    for category in ("code", "rules", "domain"):
        name, fn = make_specialist(category)
        builder.add_node(name, fn)
    builder.add_edge(START, "supervisor")
    builder.add_edge("writer", END)
    return builder.compile()


def initial_state(task: str) -> dict:
    return {"messages": [HumanMessage(content=task)], "query": "", "hops": 0, "trail": []}
