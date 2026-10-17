from crewai import Process

from app.crew_pipeline import SearchDocsTool, build_crew
from app.roles import GRADER, RETRIEVER, SYNTHESISER
from app.schemas import GradeReport


def test_crew_has_three_role_agents_in_a_sequential_process(crew_factory):
    crew, _ = build_crew(crew_factory)
    assert [a.role for a in crew.agents] == [RETRIEVER.role, GRADER.role, SYNTHESISER.role]
    assert crew.process == Process.sequential
    assert len(crew.tasks) == 3


def test_agent_fields_come_straight_from_the_shared_roles(crew_factory):
    crew, _ = build_crew(crew_factory)
    for agent, role in zip(crew.agents, (RETRIEVER, GRADER, SYNTHESISER)):
        assert (agent.role, agent.goal, agent.backstory) == (role.role, role.goal, role.backstory)
        assert agent.allow_delegation is False


def test_only_the_retriever_has_a_tool_and_it_is_search_docs(crew_factory):
    crew, tool = build_crew(crew_factory)
    retriever, grader, synthesiser = crew.agents
    assert [t.name for t in retriever.tools] == ["search_docs"]
    assert isinstance(retriever.tools[0], SearchDocsTool)
    assert grader.tools == [] and synthesiser.tools == []


def test_task_context_chain_and_typed_grader_output(crew_factory):
    crew, _ = build_crew(crew_factory)
    retrieve, grade, answer = crew.tasks
    assert not isinstance(retrieve.context, list)         # the first task depends on nothing (CrewAI's NOT_SPECIFIED sentinel)
    assert grade.context == [retrieve]                    # grader sees the retriever's passages
    assert answer.context == [retrieve, grade]            # synthesiser sees passages AND grades
    assert grade.output_pydantic is GradeReport


def test_each_agent_gets_its_own_llm_instance(crew_factory):
    build_crew(crew_factory)
    assert len(crew_factory.made) == 3 and len({id(m) for m in crew_factory.made}) == 3


def test_search_tool_returns_the_expected_passages():
    from app.retrieval import BM25Retriever

    tool = SearchDocsTool(retriever=BM25Retriever())
    out = tool._run("99.4% uptime SLA credit")
    assert "[uptime-sla]" in out
    assert tool.queries == ["99.4% uptime SLA credit"]
