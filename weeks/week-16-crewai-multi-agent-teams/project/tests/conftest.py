from __future__ import annotations

import os

# keep CrewAI quiet and offline for every test (must be set before crewai is imported)
os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
os.environ.setdefault("OTEL_SDK_DISABLED", "true")
# the LLM clients are constructed but never called in these tests, so a placeholder key is enough
os.environ.setdefault("OPENAI_API_KEY", "sk-placeholder-never-sent")

import pytest
from crewai import LLM


class CrewLLMFactory:
    """Hands out a NEW real CrewAI LLM per call (one per agent). Nothing here calls the network."""

    def __init__(self) -> None:
        self.made: list[LLM] = []

    def __call__(self) -> LLM:
        llm = LLM(model="openai/gpt-4o-mini", temperature=0)
        self.made.append(llm)
        return llm


@pytest.fixture
def crew_factory() -> CrewLLMFactory:
    return CrewLLMFactory()
