"""Typed contracts shared by the supervisor, the classifiers and the eval.

``Route`` is what the supervisor LLM must return. Pydantic enforces it: ``category`` can only
be one of the three agents (a typo like "codes" fails validation instead of silently routing
nowhere) and ``confidence`` is clamped to [0, 1]. Passed to ``llm.with_structured_output`` it
also becomes the JSON schema the model is constrained to.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Category = Literal["code", "rules", "domain"]
CATEGORIES: tuple[str, ...] = ("code", "rules", "domain")

# Below this the supervisor does not guess -- it asks the human (Week 14 task).
CONFIDENCE_THRESHOLD = 0.6


class Route(BaseModel):
    category: Category = Field(description="Which sub-agent should handle the query.")
    confidence: float = Field(ge=0.0, le=1.0, description="How sure you are about `category`, 0-1.")
    reasoning: str = Field(default="", description="One short sentence justifying the choice.")


class Hit(BaseModel):
    """One retrieved snippet. Stubs fill these in now; real indexes will in Month 5."""

    source: str
    text: str
