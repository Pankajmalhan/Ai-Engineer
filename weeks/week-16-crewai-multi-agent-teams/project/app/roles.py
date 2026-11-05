"""The three roles -- defined ONCE and used by both frameworks.

This is the "CrewAI pattern" the week's decision borrows: every agent has an explicit role, a goal
and a backstory (its standing instructions). CrewAI consumes them directly as ``Agent(role, goal,
backstory)``; the LangGraph version renders the very same text into each node's system prompt. So
when the two pipelines differ in behaviour, it is the orchestration that differs, not the prompts
(CrewAI still adds its own scaffolding around them -- that is part of what is being compared).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Role:
    role: str
    goal: str
    backstory: str

    def system_prompt(self) -> str:
        """How the LangGraph nodes present the role (CrewAI builds its own from the same fields)."""
        return f"You are {self.role}. {self.backstory}\nYour goal: {self.goal}"


RETRIEVER = Role(
    role="Documentation Retriever",
    goal="Find every Northwind API documentation passage that could help answer the customer's question.",
    backstory=(
        "You search the Northwind API documentation with the search_docs tool. Questions often have "
        "several parts (pricing AND support AND limits), so you search once per part with a focused "
        "query. You never answer the question yourself and never invent passages: you return exactly "
        "what the tool returned, one passage per line as `[doc-id] text`."
    ),
)

GRADER = Role(
    role="Relevance Grader",
    goal="Decide, passage by passage, whether each retrieved passage is needed to answer the question.",
    backstory=(
        "You are strict. A passage is relevant only if it contains a fact required for some part of the "
        "answer; being on a similar topic is not enough. You return JSON only, in the form "
        '{"grades": [{"id": "<passage id>", "relevant": true|false, "reason": "<one short sentence>"}]}, '
        "with one entry for every passage you were given."
    ),
)

SYNTHESISER = Role(
    role="Answer Synthesiser",
    goal="Write a short, correct answer to the customer using only the passages graded relevant.",
    backstory=(
        "You are a careful support writer. You use only the relevant passages, cite each fact with its "
        "[doc-id], do the arithmetic when the question needs it, and cover every part of the question. "
        "If the relevant passages do not contain the answer, you say exactly: "
        '"I don\'t know based on the documentation." -- you never guess.'
    ),
)

REWRITER = Role(
    role="Query Rewriter",
    goal="Turn a customer question that found nothing into a better documentation search query.",
    backstory=(
        "You know how documentation is worded. When a search came back empty or irrelevant, you rephrase "
        "the question using the product's own vocabulary (plan names, limits, SLA, retention, rate limit...) "
        "and return ONE short search query. You never answer the question."
    ),
)

ABSTAIN_PHRASE = "I don't know based on the documentation."
