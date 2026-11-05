"""The Deep Agent: the same audit, built on the `deepagents` harness instead of a hand-rolled graph.

What the harness adds on top of the bare LangGraph agent loop (verified against deepagents 0.7+):

* a virtual filesystem (`ls read_file write_file edit_file delete glob grep`) stored in agent
  state -- scratch space and a place to put the deliverable, instead of the context window;
* a `task` tool that spawns a sub-agent with a fresh, isolated context and returns ONLY its
  final message to the parent;
* planning via `write_todos` -- NOT on by default: it comes from `TodoListMiddleware`, which
  this module passes explicitly (the roadmap text says "default planning tool"; it isn't).

The parent is given no repository tools at all, so it has to delegate -- that is what keeps the
raw file contents out of its thread.
"""

from __future__ import annotations

from langchain.agents.middleware import TodoListMiddleware
from langchain_core.language_models import BaseChatModel
from langgraph.graph.state import CompiledStateGraph

from app.tools import lookup_rules, read_code, search_code, search_domain_docs

PARENT_PROMPT = """You lead a codebase audit. You cannot read the repository yourself: delegate every lookup
to a sub-agent with the `task` tool and give each a self-contained brief (sub-agents see nothing else).
Ask for FINDINGS ONLY -- file:line, rule ids, quoted values -- never raw file dumps.
Plan with write_todos first. When you have every finding, write the report to /audit.md with write_file."""

_BRIEF = "Reply in under 150 words with findings only: cite file:line, rule ids and exact values. No file dumps."

SUBAGENT_SPECS: list[dict] = [
    {
        "name": "code-researcher",
        "description": "Finds where a feature is implemented and tested, and reports the code facts (constants, signatures, missing tests).",
        "system_prompt": f"You research source code. Use search_code, then read_code on the relevant files. {_BRIEF}",
        "tools": [search_code, read_code],
    },
    {
        "name": "rules-checker",
        "description": "Checks given code against the team's coding rules and lists each violated rule id with evidence.",
        "system_prompt": (
            "You check code against the team rules. Call lookup_rules, read_code the files you were told about, "
            f"then list ONLY rules that are actually violated, with the evidence. {_BRIEF}"
        ),
        "tools": [lookup_rules, read_code],
    },
    {
        "name": "policy-analyst",
        "description": "Looks up the documented domain policy for a topic and returns the exact stated values.",
        "system_prompt": f"You read domain documentation. Use search_domain_docs and quote the stated values exactly. {_BRIEF}",
        "tools": [search_domain_docs],
    },
]


def build_deep_agent(
    model: BaseChatModel,
    *,
    planning: bool = True,
    subagent_models: dict[str, BaseChatModel] | None = None,
) -> CompiledStateGraph:
    """``subagent_models`` overrides the model per sub-agent name (scripted tests need one each --
    a sub-agent otherwise reuses the parent's model instance)."""
    from deepagents import create_deep_agent

    specs = [{**spec, **({"model": subagent_models[spec["name"]]} if subagent_models and spec["name"] in subagent_models else {})} for spec in SUBAGENT_SPECS]
    return create_deep_agent(
        model=model,
        tools=[],
        system_prompt=PARENT_PROMPT,
        subagents=specs,
        middleware=[TodoListMiddleware()] if planning else [],
        name="audit-lead",
    )
