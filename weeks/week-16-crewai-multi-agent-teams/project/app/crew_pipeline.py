"""The assistant as a CrewAI crew: Retriever -> Relevance Grader -> Answer Synthesiser.

CrewAI's model: you describe WHO does the work (``Agent``: role, goal, backstory, tools) and WHAT
each unit of work is (``Task``: description, expected output, which earlier tasks' outputs it can
see). A ``Crew`` with ``Process.sequential`` then runs the tasks in order, each agent running its own
LLM loop. There is no graph to draw: the control flow is "the list of tasks, in order".
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from typing import Any

# CrewAI sends anonymous usage telemetry unless told not to. This is a local learning harness over a
# fixture corpus, so keep it off (must be set before crewai is imported).
os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
os.environ.setdefault("OTEL_SDK_DISABLED", "true")

from crewai import Agent, Crew, Process, Task  # noqa: E402
from crewai.tools import BaseTool  # noqa: E402
from pydantic import BaseModel, ConfigDict, Field  # noqa: E402

from app.retrieval import BM25Retriever  # noqa: E402
from app.roles import GRADER, RETRIEVER, SYNTHESISER, Role  # noqa: E402
from app.schemas import GradeReport, format_passages, parse_passages  # noqa: E402
from app.types import PipelineResult  # noqa: E402

TOP_K = 4


class SearchDocsInput(BaseModel):
    query: str = Field(description="A focused search query for ONE part of the customer's question.")


class SearchDocsTool(BaseTool):
    """The Retriever's only tool: BM25 over the Northwind corpus (same retriever as Weeks 5-13)."""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str = "search_docs"
    description: str = "Search the Northwind API documentation. Returns the top passages as lines of `[doc-id] text`."
    args_schema: type[BaseModel] = SearchDocsInput
    retriever: Any = None
    top_k: int = TOP_K
    queries: list[str] = Field(default_factory=list)  # what the agent actually searched for
    returned_ids: list[str] = Field(default_factory=list)  # every passage id the tool handed back, in order

    def _run(self, query: str) -> str:
        self.queries.append(query)
        passages = {d.id: d.text for d in self.retriever.retrieve(query, k=self.top_k)}
        self.returned_ids.extend(pid for pid in passages if pid not in self.returned_ids)
        return format_passages(passages)


def _agent(role: Role, llm: Any, tools: list | None = None) -> Agent:
    return Agent(
        role=role.role,
        goal=role.goal,
        backstory=role.backstory,
        tools=tools or [],
        llm=llm,
        allow_delegation=False,  # a strict pipeline: no agent hands work to another
        verbose=False,
    )


def build_crew(llm_factory: Callable[[], Any], retriever: BM25Retriever | None = None, top_k: int = TOP_K) -> tuple[Crew, SearchDocsTool]:
    """``llm_factory`` is called once PER AGENT. CrewAI sums token usage across agents, so sharing a
    single LLM object between three agents would count every call three times. (Separate instances also
    mean each role could run a different model -- e.g. a cheap one for grading.)"""
    tool = SearchDocsTool(retriever=retriever or BM25Retriever(), top_k=top_k)
    retriever_agent = _agent(RETRIEVER, llm_factory(), [tool])
    grader_agent = _agent(GRADER, llm_factory())
    synthesiser_agent = _agent(SYNTHESISER, llm_factory())

    retrieve = Task(
        description=f"Customer question: {{question}}\nSearch the documentation for passages that could help answer it. Use search_docs once per part of the question.",
        expected_output="The retrieved passages, one per line, formatted exactly as `[doc-id] passage text`.",
        agent=retriever_agent,
    )
    grade = Task(
        description=f"Customer question: {{question}}\nGrade every retrieved passage for relevance to the question.",
        expected_output="A JSON object with a `grades` list containing one entry per retrieved passage: id, relevant, reason.",
        agent=grader_agent,
        context=[retrieve],
        output_pydantic=GradeReport,
    )
    answer = Task(
        description=f"Customer question: {{question}}\nAnswer the customer using only the passages graded relevant.",
        expected_output="A short, correct answer that cites the [doc-id] of each fact it uses.",
        agent=synthesiser_agent,
        context=[retrieve, grade],
    )
    crew = Crew(agents=[retriever_agent, grader_agent, synthesiser_agent], tasks=[retrieve, grade, answer], process=Process.sequential, verbose=False)
    return crew, tool


class CrewPipeline:
    framework = "crewai"

    def __init__(self, llm_factory: Callable[[], Any], retriever: BM25Retriever | None = None, top_k: int = TOP_K):
        self.llm_factory = llm_factory
        self.retriever = retriever or BM25Retriever()
        self.top_k = top_k

    def run(self, question: str) -> PipelineResult:
        started = time.perf_counter()
        try:
            crew, _tool = build_crew(self.llm_factory, self.retriever, self.top_k)
            output = crew.kickoff(inputs={"question": question})
            retrieved = list(parse_passages(output.tasks_output[0].raw))
            report = output.tasks_output[1].pydantic
            kept = report.kept_ids if report is not None else []
            usage = getattr(output, "token_usage", None)
            return PipelineResult(
                framework=self.framework,
                question=question,
                answer=output.raw,
                retrieved_ids=retrieved,
                kept_ids=kept,
                latency_s=time.perf_counter() - started,
                llm_calls=int(getattr(usage, "successful_requests", 0) or 0),
                total_tokens=int(getattr(usage, "total_tokens", 0) or 0) or None,
            )
        except Exception as exc:  # one bad query must not sink a 20-query run
            return PipelineResult(self.framework, question, answer="", latency_s=time.perf_counter() - started, error=f"{type(exc).__name__}: {exc}")
