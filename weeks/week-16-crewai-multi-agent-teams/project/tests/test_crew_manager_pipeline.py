from crewai import Process

from app.crew_manager_pipeline import MANAGER, REWRITER, RecordGradesTool, build_manager_crew
from app.crew_pipeline import SearchDocsTool
from app.roles import ABSTAIN_PHRASE, GRADER, RETRIEVER, SYNTHESISER


def test_hierarchical_crew_with_one_agentless_task_and_a_separate_manager(crew_factory):
    crew, *_ = build_manager_crew(crew_factory)
    assert crew.process == Process.hierarchical
    assert len(crew.tasks) == 1 and crew.tasks[0].agent is None  # the manager owns it
    assert crew.manager_agent.role == MANAGER.role
    assert crew.manager_agent not in crew.agents
    assert crew.manager_agent.allow_delegation is True and not crew.manager_agent.tools


def test_specialists_are_the_shared_roles_plus_the_rewriter_and_cannot_delegate(crew_factory):
    crew, *_ = build_manager_crew(crew_factory)
    assert [a.role for a in crew.agents] == [RETRIEVER.role, REWRITER.role, GRADER.role, SYNTHESISER.role]
    assert all(a.allow_delegation is False for a in crew.agents)


def test_each_specialist_has_only_its_own_tool(crew_factory):
    crew, search, record = build_manager_crew(crew_factory)
    retriever, rewriter, grader, synthesiser = crew.agents
    assert [type(t) for t in retriever.tools] == [SearchDocsTool]
    assert [type(t) for t in grader.tools] == [RecordGradesTool]
    assert rewriter.tools == [] and synthesiser.tools == []


def test_manager_and_every_specialist_get_their_own_llm_instance(crew_factory):
    build_manager_crew(crew_factory)
    assert len(crew_factory.made) == 5 and len({id(m) for m in crew_factory.made}) == 5


def test_routing_policy_names_every_step_and_the_abstain_sentence(crew_factory):
    crew, *_ = build_manager_crew(crew_factory)
    text = crew.tasks[0].description
    for role in (RETRIEVER.role, GRADER.role, SYNTHESISER.role, REWRITER.role):
        assert role in text
    assert ABSTAIN_PHRASE in text and "{question}" in text


def test_record_grades_tool_turns_the_graders_call_into_a_typed_report():
    tool = RecordGradesTool()
    msg = tool._run([{"id": "uptime-sla", "relevant": True, "reason": "credit"}, {"id": "billing", "relevant": False}])
    assert tool.reports[-1].kept_ids == ["uptime-sla"]
    assert "uptime-sla" in msg


def test_search_tool_remembers_every_returned_id_without_duplicates():
    from app.retrieval import BM25Retriever

    tool = SearchDocsTool(retriever=BM25Retriever())
    tool._run("99.4% uptime SLA credit")
    tool._run("uptime SLA credit")
    assert len(tool.returned_ids) == len(set(tool.returned_ids)) and "uptime-sla" in tool.returned_ids
