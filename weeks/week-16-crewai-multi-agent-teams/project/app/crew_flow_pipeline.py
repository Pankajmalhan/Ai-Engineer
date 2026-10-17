"""The assistant as a CrewAI FLOW: Python decides the path, small crews do the LLM work.

    crew_pipeline.py          sequential crew : fixed task order, the LLM runs everything
    crew_manager_pipeline.py  hierarchical    : a manager LLM decides who works next
    crew_flow_pipeline.py     flow            : YOUR CODE decides what runs next; crews are just steps

    @start    retrieve        plain function (BM25) ........................ no LLM
    @listen   grade           Crew #1: one Grader agent, one task ........... GradeReport
    @router   check_grades    if/else in Python
                 |-- "answer" --------------------------------------------> synthesise
                 '-- "retry"  --> retry_search --> @router check_retry
                                    (Crew #2: Query Rewriter,                |-- "answer"  -> synthesise
                                     retrieve again,                         '-- "abstain" -> abstain
                                     Crew #3: Grader again)
    @listen("answer")   synthesise   Crew #4: one Synthesiser agent, one task
    @listen("abstain")  say_dont_know plain function, fixed sentence, no LLM

It is the same graph as ``graph_pipeline.py`` plus a one-time retry, written with CrewAI's own decorators:

* ``@start()`` marks where the flow begins.
* ``@listen(method)`` runs when ``method`` finishes and receives its return value.
* ``@router(method)`` returns a LABEL string; ``@listen("label")`` methods run for that label.
  (A label may not equal any method name, or CrewAI rejects the flow as a possible infinite loop.)
  The branch is ordinary Python, so it is readable, testable, and the model cannot skip or repeat it.
* ``self.state`` is one typed object (a pydantic model) shared by all steps.

Each crew is small and built fresh inside its step, with its own LLM instance. A crew's usage is NOT
added to the flow automatically, so every step adds it to ``state`` itself (``_count``).
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from typing import Any

os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
os.environ.setdefault("OTEL_SDK_DISABLED", "true")

from crewai import Agent, Crew, Process, Task  # noqa: E402
from crewai.flow.flow import Flow, listen, router, start  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from app.retrieval import BM25Retriever  # noqa: E402
from app.roles import ABSTAIN_PHRASE, GRADER, REWRITER, SYNTHESISER, Role  # noqa: E402
from app.schemas import GradeReport, format_passages  # noqa: E402
from app.types import PipelineResult  # noqa: E402

TOP_K = 4


class SupportState(BaseModel):
    question: str = ""
    search_query: str = ""  # what we search with; the Query Rewriter replaces it on the retry
    passages: dict[str, str] = Field(default_factory=dict)
    retrieved_ids: list[str] = Field(default_factory=list)  # union over every search
    kept_ids: list[str] = Field(default_factory=list)  # the LAST grading round
    retried: bool = False
    answer: str = ""
    llm_calls: int = 0
    total_tokens: int = 0


class SupportFlow(Flow[SupportState]):
    llm_factory: Any = None  # a NEW LLM per agent, called inside each step
    retriever: Any = None
    top_k: int = TOP_K

    # ---- helpers (not flow steps) ---------------------------------------------------------------
    def _run_crew(self, role: Role, description: str, expected_output: str, inputs: dict[str, str], output_pydantic: type[BaseModel] | None = None):
        """One agent, one task, one crew -- and add its usage to the flow state."""
        agent = Agent(role=role.role, goal=role.goal, backstory=role.backstory, llm=self.llm_factory(), allow_delegation=False, verbose=False)
        task = Task(description=description, expected_output=expected_output, agent=agent, output_pydantic=output_pydantic)
        output = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=False).kickoff(inputs=inputs)
        usage = getattr(output, "token_usage", None)
        self.state.llm_calls += int(getattr(usage, "successful_requests", 0) or 0)
        self.state.total_tokens += int(getattr(usage, "total_tokens", 0) or 0)
        return output

    def _search(self) -> None:
        found = {d.id: d.text for d in self.retriever.retrieve(self.state.search_query, k=self.top_k)}
        self.state.passages = found
        self.state.retrieved_ids += [pid for pid in found if pid not in self.state.retrieved_ids]

    def _grade(self) -> None:
        output = self._run_crew(
            GRADER,
            description="Customer question: {question}\n\nRetrieved passages:\n{passages}\n\nGrade every retrieved passage for relevance to the question.",
            expected_output="A JSON object with a `grades` list containing one entry per retrieved passage: id, relevant, reason.",
            inputs={"question": self.state.question, "passages": format_passages(self.state.passages)},
            output_pydantic=GradeReport,
        )
        self.state.kept_ids = output.pydantic.kept_ids if output.pydantic is not None else []

    # ---- the flow ---------------------------------------------------------------------------------
    @start()
    def retrieve(self):
        self.state.search_query = self.state.question
        self._search()

    @listen(retrieve)
    def grade(self):
        self._grade()

    @router(grade)
    def check_grades(self):
        return "answer" if self.state.kept_ids else "retry"

    @listen("retry")
    def retry_search(self):
        """Runs at most once: no step can send the flow back here."""
        self.state.retried = True
        rewritten = self._run_crew(
            REWRITER,
            description="Customer question: {question}\nThe first search found nothing relevant. Write ONE better documentation search query.",
            expected_output="One short search query and nothing else.",
            inputs={"question": self.state.question},
        )
        self.state.search_query = rewritten.raw.strip().strip('"') or self.state.question
        self._search()
        self._grade()

    @router(retry_search)
    def check_retry(self):
        return "answer" if self.state.kept_ids else "abstain"

    @listen("answer")
    def synthesise(self):
        kept = {pid: self.state.passages[pid] for pid in self.state.kept_ids if pid in self.state.passages}
        output = self._run_crew(
            SYNTHESISER,
            description="Customer question: {question}\n\nRelevant passages:\n{passages}\n\nAnswer the customer using only these passages.",
            expected_output="A short, correct answer that cites the [doc-id] of each fact it uses.",
            inputs={"question": self.state.question, "passages": format_passages(kept)},
        )
        self.state.answer = output.raw

    @listen("abstain")
    def say_dont_know(self):
        self.state.answer = ABSTAIN_PHRASE


class CrewFlowPipeline:
    framework = "crewai-flow"

    def __init__(self, llm_factory: Callable[[], Any], retriever: BM25Retriever | None = None, top_k: int = TOP_K):
        self.llm_factory = llm_factory
        self.retriever = retriever or BM25Retriever()
        self.top_k = top_k

    def run(self, question: str) -> PipelineResult:
        started = time.perf_counter()
        try:
            flow = SupportFlow(llm_factory=self.llm_factory, retriever=self.retriever, top_k=self.top_k, suppress_flow_events=True)
            flow.kickoff(inputs={"question": question})
            s = flow.state
            return PipelineResult(
                framework=self.framework,
                question=question,
                answer=s.answer,
                retrieved_ids=s.retrieved_ids,
                kept_ids=s.kept_ids,
                latency_s=time.perf_counter() - started,
                llm_calls=s.llm_calls,
                total_tokens=s.total_tokens or None,
            )
        except Exception as exc:  # one bad query must not sink a 20-query run
            return PipelineResult(self.framework, question, answer="", latency_s=time.perf_counter() - started, error=f"{type(exc).__name__}: {exc}")
