from crewai import LLM

from app.crew_flow_pipeline import SupportFlow
from app.retrieval import BM25Retriever
from app.roles import ABSTAIN_PHRASE


def make_flow() -> SupportFlow:
    return SupportFlow(llm_factory=lambda: LLM(model="openai/gpt-4o-mini", temperature=0), retriever=BM25Retriever(), suppress_flow_events=True)


def test_flow_declares_the_expected_steps():
    steps = set(make_flow()._definition.methods)
    assert {"retrieve", "grade", "check_grades", "retry_search", "check_retry", "synthesise", "say_dont_know"} <= steps


def test_retrieve_is_plain_code_it_searches_with_the_question_and_calls_no_llm():
    flow = make_flow()
    flow.state.question = "99.4% uptime SLA credit"
    flow.retrieve()
    assert flow.state.search_query == flow.state.question
    assert "uptime-sla" in flow.state.retrieved_ids and flow.state.llm_calls == 0


def test_first_router_branches_on_whether_the_grader_kept_anything():
    flow = make_flow()
    flow.state.kept_ids = ["uptime-sla"]
    assert flow.check_grades() == "answer"
    flow.state.kept_ids = []
    assert flow.check_grades() == "retry"


def test_second_router_never_retries_again_it_answers_or_abstains():
    flow = make_flow()
    flow.state.kept_ids = ["uptime-sla"]
    assert flow.check_retry() == "answer"
    flow.state.kept_ids = []
    assert flow.check_retry() == "abstain"


def test_abstain_step_sets_the_fixed_sentence_without_an_llm():
    flow = make_flow()
    flow.say_dont_know()
    assert flow.state.answer == ABSTAIN_PHRASE and flow.state.llm_calls == 0
