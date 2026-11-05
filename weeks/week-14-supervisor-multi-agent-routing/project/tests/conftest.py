from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.schemas import Hit, Route


class ScriptedClassifier:
    """Returns a preset Route per query substring and records every call, so tests can assert
    both *what* was routed and *how many times* the (expensive) classifier ran."""

    def __init__(self, routes: dict[str, Route], default: Route | None = None):
        self.routes = routes
        self.default = default
        self.calls: list[str] = []

    def classify(self, query: str) -> Route:
        self.calls.append(query)
        for needle, route in self.routes.items():
            if needle in query:
                return route
        if self.default is not None:
            return self.default
        raise AssertionError(f"no scripted route for {query!r}")


class CountingRetriever:
    def __init__(self, label: str):
        self.label = label
        self.calls: list[tuple[str, int]] = []
        self.__name__ = f"{label}_retriever"

    def __call__(self, query: str, k: int) -> list[Hit]:
        self.calls.append((query, k))
        return [Hit(source=f"{self.label}:1", text="hit")]


def route(category: str, confidence: float) -> Route:
    return Route(category=category, confidence=confidence, reasoning="scripted")


@pytest.fixture
def checkpointer() -> InMemorySaver:
    return InMemorySaver()
