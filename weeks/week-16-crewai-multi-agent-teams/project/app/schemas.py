"""Typed hand-offs between the three roles.

The Retriever hands over *text* (passages, one per line, ``[doc-id] text``); the Grader hands over a
``GradeReport``; the Synthesiser produces the final answer text. Both frameworks use the same
contract, so the comparison is about orchestration, not about different data shapes.
"""

from __future__ import annotations

import json
import re

from pydantic import BaseModel, Field


class Grade(BaseModel):
    id: str = Field(description="The passage id exactly as shown in brackets, e.g. 'refunds'.")
    relevant: bool = Field(description="True only if the passage contains a fact needed to answer the question.")
    reason: str = Field(default="", description="One short sentence.")


class GradeReport(BaseModel):
    grades: list[Grade]

    @property
    def kept_ids(self) -> list[str]:
        return [g.id for g in self.grades if g.relevant]


# Tolerates leading whitespace and list bullets ("- [id] ...", "* [id] ..."), which models add freely.
PASSAGE_LINE = re.compile(r"^[ \t>*-]*\[(?P<id>[a-z0-9][a-z0-9-]*)\]\s*(?P<text>.+)$", re.MULTILINE)


def parse_passages(text: str) -> dict[str, str]:
    """``[id] text`` lines -> {id: text}. Order of first appearance is kept (dicts are ordered)."""
    return {m["id"]: m["text"].strip() for m in PASSAGE_LINE.finditer(text)}


def format_passages(passages: dict[str, str]) -> str:
    return "\n".join(f"[{pid}] {text}" for pid, text in passages.items())


def parse_grade_report(text: str) -> GradeReport:
    """Tolerant JSON extraction: models wrap JSON in code fences or add a sentence around it."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError(f"no JSON object in grader output: {text[:120]!r}")
    return GradeReport.model_validate(json.loads(text[start : end + 1]))
