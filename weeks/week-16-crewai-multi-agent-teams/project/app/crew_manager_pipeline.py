"""The assistant as a HIERARCHICAL crew: a manager agent decides who works next.

    sequential crew (crew_pipeline.py)         hierarchical crew (this file)
    ----------------------------------         -----------------------------
    task list in fixed order                   ONE task: "resolve this customer question"
    each task has its own agent                no agent on the task; a MANAGER agent owns it
    code decides the order                     the manager LLM decides the order, by calling
                                               "Delegate work to coworker" / "Ask question to coworker"

Team (all specialists have ``allow_delegation=False``; only the manager delegates):

    Support Lead (manager) --+--> Documentation Retriever   tool: search_docs
                             +--> Query Rewriter            rephrases a question that found nothing
                             +--> Relevance Grader          tool: record_grades
                             +--> Answer Synthesiser

The routing policy lives in the task description, in plain English:

    retrieve -> grade -> any relevant? --yes--> synthesise
                              |no
                              +--> rewrite -> retrieve -> grade (ONE retry only) --> still nothing? abstain

Two things to keep in mind when reading the results:

* The branch and the "one retry only" limit are ENFORCED BY A PROMPT, not by code. ``max_iter`` on the
  manager is the only hard stop.
* Every hand-off goes through the manager's tool arguments: to give the Grader the passages, the manager
  LLM must copy them into the ``context`` field of its delegation call. In the sequential crew CrewAI
  pastes the previous task's output itself (``context=[...]``), so nothing can be mistyped.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from crewai import Agent, Crew, Process, Task
from crewai.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from app.crew_pipeline import TOP_K, SearchDocsTool, _agent
from app.retrieval import BM25Retriever
from app.roles import ABSTAIN_PHRASE, GRADER, RETRIEVER, REWRITER, SYNTHESISER, Role
from app.schemas import Grade, GradeReport
from app.types import PipelineResult

MANAGER = Role(
    role="Support Lead",
    goal="Get the customer a correct answer from the documentation, or an honest 'I don't know'.",
    backstory=(
        "You run a small support team and do none of the work yourself. You delegate each step to the right "
        "coworker, give them everything they need (copy passages and the question into the delegation "
        "context verbatim), read what they send back, and decide the next step. You never answer from your "
        "own knowledge."
    ),
)

# the Grader's shared role says "return JSON only"; here it must submit through a tool so the result is typed
GRADER_WITH_TOOL = replace(
    GRADER,
    backstory=GRADER.backstory + " Submit your verdict by calling record_grades exactly once, then reply with the ids you kept.",
)


class RecordGradesTool(BaseTool):
    """The Grader's way to hand over a typed ``GradeReport``: the call lands here, not in free text."""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str = "record_grades"
    description: str = "Record the relevance verdict for every passage you were given. Call it once."
    args_schema: type[BaseModel] = GradeReport
    reports: list[GradeReport] = Field(default_factory=list)  # one per call; the manager may grade twice (retry)

    def _run(self, grades: list[Any]) -> str:
        report = GradeReport(grades=[Grade.model_validate(g) for g in grades])
        self.reports.append(report)
        return f"Recorded. Relevant: {', '.join(report.kept_ids) or 'none'}."


def _manager_task_description() -> str:
    return (
        "Customer question: {question}\n\n"
        "Resolve this question by delegating to your coworkers. Follow this policy:\n"
        "1. Ask the Documentation Retriever to search for passages. Pass the customer's question.\n"
        "2. Give ALL the returned passages (verbatim) and the question to the Relevance Grader.\n"
        "3. If the Grader kept at least one passage: give the question and ONLY the kept passages to the "
        "Answer Synthesiser, and return its answer.\n"
        "4. If the Grader kept nothing and you have not retried yet: ask the Query Rewriter for a better "
        "search query, search again with it, and grade again (step 2). Retry at most ONCE.\n"
        f"5. If still nothing is relevant, do not call the Answer Synthesiser: return exactly: {ABSTAIN_PHRASE}"
    )


def build_manager_crew(
    llm_factory: Callable[[], Any], retriever: BM25Retriever | None = None, top_k: int = TOP_K, max_manager_steps: int = 15
) -> tuple[Crew, SearchDocsTool, RecordGradesTool]:
    """``llm_factory`` is called once per agent INCLUDING the manager (5 instances), for the same reason as
    in ``crew_pipeline.build_crew``: CrewAI sums usage per agent, so a shared LLM object would be counted
    once per agent."""
    search = SearchDocsTool(retriever=retriever or BM25Retriever(), top_k=top_k)
    record = RecordGradesTool()

    specialists = [
        _agent(RETRIEVER, llm_factory(), [search]),
        _agent(REWRITER, llm_factory()),
        _agent(GRADER_WITH_TOOL, llm_factory(), [record]),
        _agent(SYNTHESISER, llm_factory()),
    ]
    manager = Agent(
        role=MANAGER.role,
        goal=MANAGER.goal,
        backstory=MANAGER.backstory,
        llm=llm_factory(),
        allow_delegation=True,  # a manager's only job is to delegate (it must have NO tools of its own)
        max_iter=max_manager_steps,  # the only hard limit on the manager's routing loop
        verbose=False,
    )
    # No agent on the task: in a hierarchical process the manager owns it and hands out the pieces.
    resolve = Task(
        description=_manager_task_description(),
        expected_output="The final answer to the customer, citing the [doc-id] of each fact, or the exact 'I don't know' sentence.",
    )
    crew = Crew(agents=specialists, tasks=[resolve], process=Process.hierarchical, manager_agent=manager, verbose=False)
    return crew, search, record


class CrewManagerPipeline:
    framework = "crewai-manager"

    def __init__(self, llm_factory: Callable[[], Any], retriever: BM25Retriever | None = None, top_k: int = TOP_K):
        self.llm_factory = llm_factory
        self.retriever = retriever or BM25Retriever()
        self.top_k = top_k

    def run(self, question: str) -> PipelineResult:
        started = time.perf_counter()
        try:
            crew, search, record = build_manager_crew(self.llm_factory, self.retriever, self.top_k)
            output = crew.kickoff(inputs={"question": question})
            usage = getattr(output, "token_usage", None)
            return PipelineResult(
                framework=self.framework,
                question=question,
                answer=output.raw,
                retrieved_ids=list(search.returned_ids),  # union over every search the Retriever ran
                kept_ids=record.reports[-1].kept_ids if record.reports else [],  # the LAST grading round
                latency_s=time.perf_counter() - started,
                llm_calls=int(getattr(usage, "successful_requests", 0) or 0),
                total_tokens=int(getattr(usage, "total_tokens", 0) or 0) or None,
            )
        except Exception as exc:  # one bad query must not sink a 20-query run
            return PipelineResult(self.framework, question, answer="", latency_s=time.perf_counter() - started, error=f"{type(exc).__name__}: {exc}")
