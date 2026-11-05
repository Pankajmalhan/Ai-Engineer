"""The harness: what the model is given, what lands in state, what stays out of the parent thread."""


from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app import offline
from app.deep import SUBAGENT_SPECS, build_deep_agent
from app.offline import ScriptedChatModel, tool_call
from app.runners import run_deep
from app.task import DEEP_SUFFIX, TASK

# Text that exists only in RAW tool output (file bodies / chunk headers), never in a sub-agent's summary.
RAW_FILE_BODY = "Session management for the web app"
RAW_CHUNK_HEADER = "--- code/src/auth/session.py:"


def invoke(lead=None, subs=None, planning=True):
    if lead is None:
        lead, subs = offline.deep_models()
    agent = build_deep_agent(lead, planning=planning, subagent_models=subs)
    out = agent.invoke({"messages": [HumanMessage(content=TASK + DEEP_SUFFIX)]}, config={"recursion_limit": 100})
    return out, lead, subs


def test_parent_gets_the_harness_tools_but_no_repository_tools():
    _, lead, _ = invoke()
    assert {"task", "write_file", "read_file", "edit_file", "ls", "write_todos"} <= set(lead.bound_tools)
    # it must delegate: it has no way to read the repo itself
    assert not {"search_code", "read_code", "lookup_rules", "search_domain_docs"} & set(lead.bound_tools)


def test_write_todos_is_opt_in_not_a_default():
    _, lead, _ = invoke(planning=False)
    assert "write_todos" not in lead.bound_tools
    assert "task" in lead.bound_tools


def test_each_subagent_only_gets_its_own_repository_tools():
    _, _, subs = invoke()
    repo_tools = {"search_code", "read_code", "lookup_rules", "search_domain_docs"}
    for spec in SUBAGENT_SPECS:
        bound = set(subs[spec["name"]].bound_tools)
        assert bound & repo_tools == {t.name for t in spec["tools"]}, spec["name"]


def test_plan_and_report_land_in_agent_state():
    out, _, _ = invoke()
    assert [t["status"] for t in out["todos"]]  # the plan exists
    assert len(out["todos"]) == 4
    assert "/audit.md" in out["files"]
    assert "Policy mismatches" in out["files"]["/audit.md"]["content"]


def test_subagent_raw_output_is_isolated_from_the_parent_thread():
    out, _, subs = invoke()
    parent_text = "\n".join(str(m.content) for m in out["messages"])
    assert RAW_FILE_BODY not in parent_text and RAW_CHUNK_HEADER not in parent_text
    # ...but the sub-agent really did receive that raw output in its own context
    code_prompt = "\n".join(str(m.content) for m in subs["code-researcher"].prompts[-1])
    assert RAW_FILE_BODY in code_prompt and RAW_CHUNK_HEADER in code_prompt
    # and what crossed back to the parent was the summary
    task_results = [str(m.content) for m in out["messages"] if isinstance(m, ToolMessage)]
    assert any("SESSION_TTL_SECONDS = 3600" in r for r in task_results)


def test_subagents_cannot_see_each_others_work_or_the_parents_plan():
    _, _, subs = invoke()
    policy_prompt = "\n".join(str(m.content) for m in subs["policy-analyst"].prompts[-1])
    assert "SEC-03" not in policy_prompt and "SESSION_SECRET" not in policy_prompt


def test_subagent_specs_are_not_mutated_by_model_overrides():
    invoke()
    assert all("model" not in spec for spec in SUBAGENT_SPECS)


def test_run_deep_scores_the_saved_report_and_counts_every_call():
    lead, subs = offline.deep_models()
    result = run_deep("deep", lead, subagent_models=subs)
    assert result.error is None and result.report_source == "file"
    assert result.score.points == 6
    m = result.metrics
    # 6 parent turns + 3 + 3 + 2 sub-agent turns: callbacks reached INSIDE the sub-agents
    assert m.llm_calls == 14
    assert m.tool_calls["task"] == 3 and m.tool_calls["write_file"] == 1 and m.tool_calls["write_todos"] == 1
    assert m.tool_calls["read_code"] == 2  # code-researcher and rules-checker each opened the file


# ---- failure modes the comparison has to be able to see ----


def test_a_report_given_in_chat_but_never_saved_is_flagged():
    lead = ScriptedChatModel(responder=lambda msgs: AIMessage(content="Audit: src/auth/session.py has SEC-03 and STYLE-12 issues."))
    result = run_deep("lazy", lead)
    assert result.report_source == "final-message (not saved)"
    assert result.score.found["SEC-03"]  # still scored, but the miss is visible


def test_a_runaway_agent_is_reported_as_an_error_not_a_crash(monkeypatch):
    monkeypatch.setattr("app.runners.RECURSION_LIMIT", 12)
    lead = ScriptedChatModel(responder=lambda msgs: tool_call("write_todos", {"todos": [{"content": "again", "status": "pending"}]}))
    result = run_deep("runaway", lead)
    assert result.error and "GraphRecursionError" in result.error
    assert result.score.points == 0 and result.report_source == "none"


def test_a_subagent_that_finds_nothing_leaves_the_fact_out_of_the_report():
    lead, subs = offline.deep_models()
    # policy analyst searches for something that is not in the docs -> no evidence -> no finding
    subs["policy-analyst"] = ScriptedChatModel(responder=offline._subagent(
        [("search_domain_docs", {"query": "kubernetes"})], offline.POLICY_FINDING, offline.POLICY_MARKERS))
    result = run_deep("blind", lead, subagent_models=subs)
    assert result.score.found["location"] and not result.score.found["max_lifetime"]
