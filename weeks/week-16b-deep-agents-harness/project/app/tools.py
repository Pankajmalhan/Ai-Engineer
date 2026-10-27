"""LangChain tool wrappers over ``app.corpus``, used by the Deep Agent's sub-agents.

The docstrings are the tool descriptions the model sees, so they say what each tool is *for*.
"""

from __future__ import annotations

from langchain_core.tools import tool

from app import corpus


@tool
def search_code(query: str) -> str:
    """Keyword-search the source code. Returns the best-matching code chunks with path:line."""
    return corpus.format_chunks(corpus.search("code", query, k=3))


@tool
def read_code(path: str) -> str:
    """Read a whole source file (with line numbers), e.g. 'code/src/auth/session.py'."""
    return corpus.read(path)


@tool
def lookup_rules(topic: str = "") -> str:
    """Return the team's coding rules (all of them, ids included). `topic` is accepted but the rulebook is short, so everything is returned."""
    return corpus.format_chunks(corpus.all_rules())


@tool
def search_domain_docs(query: str) -> str:
    """Keyword-search the domain documentation (policies, glossary, product guides)."""
    return corpus.format_chunks(corpus.search("domain", query, k=3))
