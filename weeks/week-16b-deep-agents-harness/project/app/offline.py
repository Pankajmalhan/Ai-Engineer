"""Scripted stand-ins for the LLMs, so the whole pipeline runs with no API key.

What offline mode proves: the wiring -- tools really run against the corpus, sub-agent output
really flows (and is really isolated), the loop really stops, files and todos really land in
state, the counters count. What it cannot prove: anything about model quality. The "oracle"
responders below know the right answer; they only *say* a finding if the real tool output they
were handed contains the evidence for it (``markers``), so a retrieval bug still breaks them.
So offline scores are "did the plumbing deliver the evidence", never "is the model any good".
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import BaseTool
from pydantic import Field

from app.supervisor import Step

Responder = Callable[[list[BaseMessage]], AIMessage]


class ScriptedChatModel(BaseChatModel):
    """A chat model whose replies come from ``responder(messages)``. Supports tool binding."""

    responder: Any
    bound_tools: list[str] = Field(default_factory=list)  # tool names the agent bound
    prompts: list[list[BaseMessage]] = Field(default_factory=list)  # every prompt it was shown

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        self.bound_tools = [t.name if isinstance(t, BaseTool) else (t.get("name") or t["function"]["name"]) for t in tools]
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        self.prompts.append(list(messages))
        return ChatResult(generations=[ChatGeneration(message=self.responder(messages))])


def tool_call(name: str, args: dict) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"call_{uuid.uuid4().hex[:8]}"}])


# ---- the oracle's knowledge: one finding per source, each guarded by evidence markers ----

CODE_FINDING = (
    "Implementation: code/src/auth/session.py (create_session, refresh_session); API route code/src/api/routes.py. "
    "Tests: code/tests/test_session.py only has test_refresh_extends_expiry (success path). "
    "SESSION_TTL_SECONDS = 3600. SESSION_SECRET is hard-coded. refresh_session(session, now=None) has no type hints. "
    "There is no maximum-lifetime check."
)
RULES_FINDING = (
    "Violated: SEC-03 (hard-coded SESSION_SECRET), STYLE-12 (refresh_session has no type hints), "
    "TEST-05 (no failure-path test for refresh_session / SessionExpired). REV-07 is a process rule, not checkable from code."
)
POLICY_FINDING = (
    "docs/session-policy.md: idle timeout is 30 minutes (1800 seconds); a refresh extends by 30 minutes; "
    "maximum lifetime is 12 hours (43200 seconds)."
)
CODE_MARKERS = ("SESSION_TTL_SECONDS", "SESSION_SECRET")
RULES_MARKERS = ("SEC-03", "STYLE-12", "TEST-05")
POLICY_MARKERS = ("30 minutes", "43200")


def _guarded(finding: str, evidence: str, markers: tuple[str, ...]) -> str:
    return finding if all(m in evidence for m in markers) else "No findings: the evidence did not contain what was needed."


# ---- Deep Agent: parent + three sub-agents ----


def _subagent(plan: list[tuple[str, dict]], finding: str, markers: tuple[str, ...]) -> Responder:
    def respond(messages: list[BaseMessage]) -> AIMessage:
        results = [m for m in messages if isinstance(m, ToolMessage)]
        if len(results) < len(plan):
            return tool_call(*plan[len(results)])
        return AIMessage(content=_guarded(finding, "\n".join(str(m.content) for m in results), markers))

    return respond


def _lead(messages: list[BaseMessage]) -> AIMessage:
    results = [str(m.content) for m in messages if isinstance(m, ToolMessage)]
    n = len(results)
    briefs = [
        ("code-researcher", "Find where session refresh is implemented and tested; report code facts."),
        ("rules-checker", "Check code/src/auth/session.py and its tests against the team rules; list violated rule ids."),
        ("policy-analyst", "Find the documented session timeout / refresh / maximum-lifetime policy values."),
    ]
    if n == 0:
        todos = [{"content": f"delegate to {name}", "status": "pending"} for name, _ in briefs] + [{"content": "write /audit.md", "status": "pending"}]
        return tool_call("write_todos", {"todos": todos})
    if n <= 3:
        name, brief = briefs[n - 1]
        return tool_call("task", {"description": brief, "subagent_type": name})
    if n == 4:
        code, rules, policy = results[1:4]
        report = f"# Audit\n\n## Location\n{code}\n\n## Rule violations\n{rules}\n\n## Policy mismatches\n{policy}\n"
        return tool_call("write_file", {"file_path": "/audit.md", "content": report})
    return AIMessage(content="Audit saved to /audit.md.")


def deep_models() -> tuple[ScriptedChatModel, dict[str, ScriptedChatModel]]:
    sub = {
        "code-researcher": ScriptedChatModel(responder=_subagent(
            [("search_code", {"query": "session refresh"}), ("read_code", {"path": "code/src/auth/session.py"})],
            CODE_FINDING, CODE_MARKERS)),
        "rules-checker": ScriptedChatModel(responder=_subagent(
            [("lookup_rules", {"topic": "session"}), ("read_code", {"path": "code/src/auth/session.py"})],
            RULES_FINDING, RULES_MARKERS)),
        "policy-analyst": ScriptedChatModel(responder=_subagent(
            [("search_domain_docs", {"query": "session timeout refresh lifetime policy"})],
            POLICY_FINDING, POLICY_MARKERS)),
    }
    return ScriptedChatModel(responder=_lead), sub


# ---- Supervisor: scripted planner + oracle writer ----


class ScriptedPlanner:
    def __init__(self, steps: list[Step]):
        self.steps = list(steps)
        self.calls = 0

    def next_step(self, messages: list[BaseMessage]) -> Step:
        step = self.steps[min(self.calls, len(self.steps) - 1)]
        self.calls += 1
        return step


def default_planner() -> ScriptedPlanner:
    return ScriptedPlanner([
        Step(next="code", query="session refresh implementation"),
        Step(next="rules", query="session code rules"),
        Step(next="domain", query="session timeout refresh lifetime policy"),
        Step(next="finish"),
    ])


def _writer(messages: list[BaseMessage]) -> AIMessage:
    evidence = {m.name: str(m.content) for m in messages if isinstance(m, AIMessage) and m.name}
    parts = ["# Audit"]
    if "code_agent" in evidence:
        parts.append("## Location\n" + _guarded(CODE_FINDING, evidence["code_agent"], CODE_MARKERS))
    if "rules_agent" in evidence:
        parts.append("## Rule violations\n" + _guarded(RULES_FINDING, evidence["rules_agent"], RULES_MARKERS))
    if "domain_agent" in evidence:
        parts.append("## Policy mismatches\n" + _guarded(POLICY_FINDING, evidence["domain_agent"], POLICY_MARKERS))
    return AIMessage(content="\n\n".join(parts))


def oracle_writer() -> ScriptedChatModel:
    return ScriptedChatModel(responder=_writer)
