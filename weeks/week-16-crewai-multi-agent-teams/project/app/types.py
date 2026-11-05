from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PipelineResult:
    """One query through one pipeline -- everything the comparison scores."""

    framework: str
    question: str
    answer: str
    retrieved_ids: list[str] = field(default_factory=list)  # what the Retriever role returned
    kept_ids: list[str] = field(default_factory=list)  # what the Grader role passed on
    latency_s: float = 0.0
    llm_calls: int = 0
    total_tokens: int | None = None
    error: str | None = None
