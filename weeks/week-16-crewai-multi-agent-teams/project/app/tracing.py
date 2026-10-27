"""Optional Langfuse tracing for BOTH pipelines, so one UI shows the two designs side by side.

* LangGraph: Langfuse's LangChain ``CallbackHandler`` passed in the run config -> one trace per query
  with a span per node and a generation per LLM call.
* CrewAI: the OpenInference CrewAI instrumentor emits OpenTelemetry spans (crew, agents, tasks, LLM
  calls); Langfuse's OTel exporter picks them up.
* Each query runs inside one outer span named ``<framework>:<query id>`` with tags, so the two
  frameworks' traces for the same query are easy to find and compare.

Everything here is a no-op unless LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are set, and any
failure to set tracing up is reported and ignored -- observability must never break the run.
NOTE: written against the Langfuse and OpenInference docs/type signatures; it has not been run
against a live Langfuse project (see README).
"""

from __future__ import annotations

import contextlib
import os
import sys
import uuid
from collections.abc import Iterator


def tracing_requested(env: dict[str, str] | None = None) -> bool:
    env = os.environ if env is None else env
    return bool(env.get("LANGFUSE_PUBLIC_KEY") and env.get("LANGFUSE_SECRET_KEY"))


class Tracing:
    def __init__(self, enabled: bool = False, run_id: str | None = None):
        self.enabled = False
        self.run_id = run_id or uuid.uuid4().hex[:8]
        self._client = None
        if not enabled:
            return
        try:
            from langfuse import get_client
            from openinference.instrumentation.crewai import CrewAIInstrumentor

            self._client = get_client()
            CrewAIInstrumentor().instrument()
            self.enabled = True
        except Exception as exc:  # missing extra, bad keys, SDK change...
            print(f"[tracing] disabled: {type(exc).__name__}: {exc}", file=sys.stderr)

    def langgraph_callbacks(self) -> list:
        if not self.enabled:
            return []
        from langfuse.langchain import CallbackHandler

        return [CallbackHandler()]

    @contextlib.contextmanager
    def query_span(self, framework: str, query_id: str) -> Iterator[None]:
        if not self.enabled:
            yield
            return
        from langfuse import propagate_attributes

        with self._client.start_as_current_observation(name=f"{framework}:{query_id}", as_type="span"):
            with propagate_attributes(tags=[framework, "week-16"], session_id=f"week16-{self.run_id}", trace_name=f"{framework}:{query_id}"):
                yield

    def flush(self) -> None:
        if self.enabled and self._client is not None:
            self._client.flush()
