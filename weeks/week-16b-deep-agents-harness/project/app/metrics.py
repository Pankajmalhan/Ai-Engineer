"""Counters for comparing the two architectures, collected through a LangChain callback.

Callbacks propagate into sub-agents and sub-graphs, so one handler passed in the run config sees
every model call and tool call -- including the ones the parent thread never shows. That is why
``llm_calls`` can be larger than the number of AI messages in the final thread.
"""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import BaseMessage


@dataclass
class Metrics:
    llm_calls: int = 0
    tool_calls: Counter = field(default_factory=Counter)
    input_tokens: int = 0
    output_tokens: int = 0
    token_reports: int = 0  # model calls that reported usage; 0 for scripted/offline models
    thread_chars: int = 0  # size of the PARENT thread at the end -- what the top-level agent has to carry
    elapsed_s: float = 0.0

    @property
    def total_tool_calls(self) -> int:
        return sum(self.tool_calls.values())

    @property
    def total_tokens(self) -> int | None:
        return self.input_tokens + self.output_tokens if self.token_reports else None


class RunMetrics(BaseCallbackHandler):
    def __init__(self) -> None:
        self.metrics = Metrics()
        self._t0 = time.perf_counter()

    def on_chat_model_start(self, serialized: dict[str, Any], messages: list[list[BaseMessage]], **kwargs: Any) -> None:
        self.metrics.llm_calls += 1

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        for generations in response.generations:
            for gen in generations:
                usage = getattr(getattr(gen, "message", None), "usage_metadata", None)
                if usage:
                    self.metrics.token_reports += 1
                    self.metrics.input_tokens += usage.get("input_tokens", 0)
                    self.metrics.output_tokens += usage.get("output_tokens", 0)

    def on_tool_start(self, serialized: dict[str, Any] | None, input_str: str, **kwargs: Any) -> None:
        name = kwargs.get("name") or (serialized or {}).get("name") or "unknown"
        self.metrics.tool_calls[name] += 1

    def finish(self, thread: list[BaseMessage]) -> Metrics:
        self.metrics.thread_chars = thread_chars(thread)
        self.metrics.elapsed_s = time.perf_counter() - self._t0
        return self.metrics


def thread_chars(messages: list[BaseMessage]) -> int:
    """Characters of message text in a thread (tool-call arguments included)."""
    total = 0
    for m in messages:
        total += len(m.content) if isinstance(m.content, str) else len(str(m.content))
        for call in getattr(m, "tool_calls", None) or []:
            total += len(str(call.get("args", "")))
    return total
