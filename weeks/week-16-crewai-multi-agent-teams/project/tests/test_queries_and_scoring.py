import pytest

from app.corpus import CORPUS
from app.queries import QUERIES, Query
from app.retrieval import BM25Retriever
from app.roles import ABSTAIN_PHRASE
from app.scoring import abstained, has_fact, score
from app.types import PipelineResult


def result(answer, retrieved=(), kept=(), error=None):
    return PipelineResult("x", "q", answer, list(retrieved), list(kept), error=error)


def test_query_set_is_20_with_3_unanswerable_and_unique_ids():
    assert len(QUERIES) == 20
    assert len({q.id for q in QUERIES}) == 20
    assert [q.id for q in QUERIES if not q.answerable] == ["q18", "q19", "q20"]


def test_every_answerable_query_has_facts_and_real_expected_docs():
    ids = {d.id for d in CORPUS}
    for q in QUERIES:
        if q.answerable:
            assert q.facts and q.expected_docs, q.id
            assert set(q.expected_docs) <= ids, q.id
        else:
            assert not q.facts and not q.expected_docs, q.id


def test_most_queries_need_more_than_one_fact_or_document():
    complex_ = [q for q in QUERIES if q.answerable and (len(q.expected_docs) > 1 or len(q.facts) > 1)]
    assert len(complex_) >= 12


def test_bm25_top4_covers_every_expected_doc__so_quality_gaps_come_from_grading_and_synthesis():
    retriever = BM25Retriever()
    for q in QUERIES:
        if q.answerable:
            assert set(q.expected_docs) <= {d.id for d in retriever.retrieve(q.question, k=4)}, q.id


@pytest.mark.parametrize("answer, alts, expected", [
    ("You get a **10%** credit.", ("10%",), True),
    ("a 10 % credit", ("10%", "10 %"), True),
    ("Support replies within 4 BUSINESS HOURS", ("4 business hours",), True),
    ("the old key stays valid for 24‑hour", ("24-hour",), True),   # non-breaking hyphen
    ("a 20% discount", ("10%",), False),
])
def test_has_fact_normalises_markdown_case_and_whitespace(answer, alts, expected):
    assert has_fact(answer, alts) is expected


@pytest.mark.parametrize("text", [ABSTAIN_PHRASE, "I couldn't find that.", "That is not mentioned in the docs.", "No information is available."])
def test_abstained_recognises_refusals(text):
    assert abstained(text)


def test_abstained_does_not_fire_on_a_normal_answer():
    assert not abstained("Pro gets 600 requests per minute [rate-limits].")


Q1 = next(q for q in QUERIES if q.id == "q01")   # needs 10% + 4 business hours, docs uptime-sla + support-sla
Q18 = next(q for q in QUERIES if q.id == "q18")


def test_answerable_correct_requires_all_facts():
    full = score(result("10% credit, reply in 4 business hours", ["uptime-sla", "support-sla"], ["uptime-sla", "support-sla"]), Q1)
    partial = score(result("10% credit", ["uptime-sla", "support-sla"], ["uptime-sla"]), Q1)
    assert full.correct and full.fact_recall == 1.0
    assert not partial.correct and partial.fact_recall == 0.5


def test_answerable_that_abstains_is_never_correct():
    s = score(result("I don't know based on the documentation. (10%, 4 business hours)"), Q1)
    assert not s.correct and s.abstained


def test_grader_metrics_are_computed_from_ids():
    s = score(result("x", retrieved=["uptime-sla", "support-sla", "auth", "refunds"], kept=["uptime-sla", "auth"]), Q1)
    assert s.retrieval_recall == 1.0
    assert s.kept_recall == 0.5          # kept 1 of the 2 expected docs
    assert s.kept_precision == 0.5       # 1 of the 2 kept docs was expected


def test_unanswerable_is_correct_only_when_the_pipeline_abstains():
    assert score(result(ABSTAIN_PHRASE), Q18).correct
    assert not score(result("Yes, we are SOC 2 Type II certified."), Q18).correct   # a hallucination


def test_an_errored_run_scores_zero_and_is_flagged():
    s = score(result("", error="boom"), Q1)
    assert s.error and not s.correct and s.fact_recall == 0.0
