import pytest

import app.grader as grader_mod
from app.grader import HeuristicGrader, LLMGrader, RelevanceScore, grade_batch, mean_relevance


def test_heuristic_grader_scores_exact_overlap_high():
    grader = HeuristicGrader()
    score = grader.grade(
        "What is our refund policy for annual plans?",
        "Our refund policy allows full refunds within 30 days of purchase for annual plans.",
    )
    assert score.relevance > 0.5


def test_heuristic_grader_scores_unrelated_chunk_low():
    grader = HeuristicGrader()
    score = grader.grade(
        "What is our refund policy for annual plans?",
        "The next public holiday observed company-wide is Labor Day.",
    )
    assert score.relevance < 0.3


def test_heuristic_grader_handles_empty_query():
    grader = HeuristicGrader()
    score = grader.grade("", "some chunk text")
    assert score.relevance == 0.0


def test_relevance_score_is_bounded_0_to_1():
    with pytest.raises(ValueError):
        RelevanceScore(relevance=1.5, reasoning="out of range")


def test_grade_batch_and_mean_relevance():
    grader = HeuristicGrader()
    query = "What does the SLA guarantee for uptime?"
    chunks = [
        "Our uptime SLA guarantees 99.9% availability measured monthly.",
        "The company was founded in 2018 in Austin, Texas.",
    ]
    scores = grade_batch(grader, query, chunks)
    assert len(scores) == 2
    mean = mean_relevance(scores)
    assert 0.0 <= mean <= 1.0
    assert scores[0].relevance > scores[1].relevance


def test_mean_relevance_of_empty_list_is_zero():
    assert mean_relevance([]) == 0.0


def test_llm_grader_refuses_to_construct_without_api_key(monkeypatch):
    monkeypatch.setattr(grader_mod, "ANTHROPIC_API_KEY", None)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        LLMGrader()
