"""The same three roles as a LangGraph graph.

    START -> retrieve -> grade --(any relevant?)--> synthesise -> END
                           \\--(none relevant)--> abstain ------> END

What is borrowed from CrewAI: each LLM node has an explicit role (same ``roles.py`` text).
What LangGraph adds: the control flow is *code you can read and test*. Two consequences visible here:

* ``retrieve`` is a plain function, not an agent. Deciding to call a search tool with the user's
  question is not a job for an LLM, so no LLM call (and no latency or tokens) is spent on it.
* ``grade -> abstain`` is a conditional edge: when the Grader keeps nothing, the answer is the
  fixed abstain phrase and the Synthesiser is never called.
"""

from __future__ import annotations

import time
from typing import Any, TypedDict

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from app.retrieval import BM25Retriever
from app.roles import ABSTAIN_PHRASE, GRADER, SYNTHESISER
from app.schemas import GradeReport, format_passages, parse_grade_report
from app.types import PipelineResult

TOP_K = 4


class State(TypedDict, total=False):
    question: str
    passages: dict[str, str]
    report: GradeReport
    answer: str


class CallCounter(BaseCallbackHandler):
    """Counts chat-model calls and tokens, so LangGraph's numbers are comparable with CrewAI's."""

    def __init__(self) -> None:
        self.calls = 0
        self.tokens = 0

    def on_chat_model_start(self, serialized, messages, **kwargs: Any) -> None:
        self.calls += 1

    def on_llm_end(self, response, **kwargs: Any) -> None:
        for generations in response.generations:
            for g in generations:
                usage = getattr(getattr(g, "message", None), "usage_metadata", None)
                if usage:
                    self.tokens += int(usage.get("total_tokens", 0))


def build_graph(llm: BaseChatModel, retriever: BM25Retriever | None = None, top_k: int = TOP_K):
    retriever = retriever or BM25Retriever()

    def retrieve(state: State) -> dict:
        return {"passages": {d.id: d.text for d in retriever.retrieve(state["question"], k=top_k)}}

    def grade(state: State) -> dict:
        user = f"Customer question: {state['question']}\n\nRetrieved passages:\n{format_passages(state['passages'])}"
        reply = llm.invoke([SystemMessage(content=GRADER.system_prompt()), HumanMessage(content=user)])
        return {"report": parse_grade_report(str(reply.content))}

    def route_after_grade(state: State) -> str:
        return "synthesise" if state["report"].kept_ids else "abstain"

    def synthesise(state: State) -> dict:
        kept = {pid: state["passages"][pid] for pid in state["report"].kept_ids if pid in state["passages"]}
        user = f"Customer question: {state['question']}\n\nRelevant passages:\n{format_passages(kept)}"
        reply = llm.invoke([SystemMessage(content=SYNTHESISER.system_prompt()), HumanMessage(content=user)])
        return {"answer": str(reply.content).strip()}

    def abstain(state: State) -> dict:
        return {"answer": ABSTAIN_PHRASE}

    builder = StateGraph(State)
    builder.add_node("retrieve", retrieve)
    builder.add_node("grade", grade)
    builder.add_node("synthesise", synthesise)
    builder.add_node("abstain", abstain)
    builder.add_edge(START, "retrieve")
    builder.add_edge("retrieve", "grade")
    builder.add_conditional_edges("grade", route_after_grade, {"synthesise": "synthesise", "abstain": "abstain"})
    builder.add_edge("synthesise", END)
    builder.add_edge("abstain", END)
    return builder.compile()


class GraphPipeline:
    framework = "langgraph"

    def __init__(self, llm: BaseChatModel, retriever: BM25Retriever | None = None, top_k: int = TOP_K, extra_callbacks: list | None = None):
        self.graph = build_graph(llm, retriever, top_k)
        self.extra_callbacks = extra_callbacks or []

    def run(self, question: str) -> PipelineResult:
        counter = CallCounter()
        started = time.perf_counter()
        try:
            state = self.graph.invoke({"question": question}, config={"callbacks": [counter, *self.extra_callbacks]})
            return PipelineResult(
                framework=self.framework,
                question=question,
                answer=state["answer"],
                retrieved_ids=list(state["passages"]),
                kept_ids=state["report"].kept_ids,
                latency_s=time.perf_counter() - started,
                llm_calls=counter.calls,
                total_tokens=counter.tokens or None,
            )
        except Exception as exc:
            return PipelineResult(self.framework, question, answer="", latency_s=time.perf_counter() - started, error=f"{type(exc).__name__}: {exc}")
