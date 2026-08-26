from app.crag import CragAction
from app.pipeline import CONVERSATIONAL_NOTE, QueryPipeline
from app.router import Strategy
from tests.conftest import requires_postgres


def _pipeline(pg_store):
    return QueryPipeline(store=pg_store, seed=False)  # pg_store fixture already seeds


@requires_postgres
def test_conversational_query_skips_retrieval_entirely(pg_store):
    result = _pipeline(pg_store).handle("Hi, how are you doing today?")
    assert result.strategy == Strategy.CONVERSATIONAL
    assert result.crag_result is None
    assert result.answer == CONVERSATIONAL_NOTE


@requires_postgres
def test_factual_query_in_domain_is_correct_action(pg_store):
    result = _pipeline(pg_store).handle("What is our refund policy for annual plans?")
    assert result.strategy == Strategy.FACTUAL
    assert result.crag_result.action == CragAction.CORRECT
    assert any("refund" in c.lower() for c in result.crag_result.context)


@requires_postgres
def test_code_query_in_domain_finds_the_right_chunk(pg_store):
    result = _pipeline(pg_store).handle("Why does getUserById() throw a NullPointerException?")
    assert result.strategy == Strategy.CODE
    # CORRECT or AMBIGUOUS, not INCORRECT: HeuristicGrader's literal term-overlap
    # scores this genuinely-relevant chunk ~0.67 (it explains the cause without
    # reusing the word "throw"), landing in the Ambiguous band rather than clearing
    # 0.7 -- a real illustration of concept.md's LLM-judge-vs-heuristic-grader
    # tradeoff: an LLM judge would likely score this higher and call it Correct.
    assert result.crag_result.action in (CragAction.CORRECT, CragAction.AMBIGUOUS)
    assert any("nullpointerexception" in c.lower() for c in result.crag_result.context)


@requires_postgres
def test_factual_query_out_of_domain_escalates_to_web_search(pg_store):
    result = _pipeline(pg_store).handle("What is the wingspan of an albatross?")
    assert result.strategy == Strategy.FACTUAL
    assert result.crag_result.action in (CragAction.INCORRECT, CragAction.AMBIGUOUS)
    assert result.crag_result.rewritten_query is not None
