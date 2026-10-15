"""Stub retrieval functions -- one per sub-agent.

Each returns canned, clearly-labelled hits so a test (or a reader of the trace) can tell which
agent actually ran. The signature ``(query, k) -> list[Hit]`` is the seam: in Month 5 the bodies
are replaced by real indexes (code embeddings, a rules store, domain docs) and nothing in the
graph changes.
"""

from __future__ import annotations

from collections.abc import Callable

from app.schemas import Hit

Retriever = Callable[[str, int], list[Hit]]


def search_code(query: str, k: int = 3) -> list[Hit]:
    hits = [
        Hit(source="code-stub:src/auth/session.py", text=f"def refresh_session(...)  # matched: {query!r}"),
        Hit(source="code-stub:src/api/routes.py", text="router.post('/sessions/refresh', refresh_session)"),
        Hit(source="code-stub:tests/test_session.py", text="def test_refresh_extends_expiry(): ..."),
    ]
    return hits[:k]


def lookup_rules(query: str, k: int = 3) -> list[Hit]:
    hits = [
        Hit(source="rules-stub:STYLE-12", text=f"Public functions must have type hints.  # matched: {query!r}"),
        Hit(source="rules-stub:SEC-03", text="Secrets must never be committed; use the secret manager."),
        Hit(source="rules-stub:REV-07", text="Every PR needs one approving review before merge."),
    ]
    return hits[:k]


def search_domain_docs(query: str, k: int = 3) -> list[Hit]:
    hits = [
        Hit(source="domain-stub:glossary/session", text=f"A session is a signed-in period for one user.  # matched: {query!r}"),
        Hit(source="domain-stub:guides/billing", text="Invoices are generated on the first of each month."),
        Hit(source="domain-stub:guides/onboarding", text="New accounts start on the free tier for 14 days."),
    ]
    return hits[:k]
