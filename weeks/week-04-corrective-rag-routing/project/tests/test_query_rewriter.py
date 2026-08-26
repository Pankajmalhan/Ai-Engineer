import pytest

import app.query_rewriter as rewriter_mod
from app.query_rewriter import HeuristicRewriter, LLMRewriter


def test_heuristic_rewriter_drops_question_words_and_punctuation():
    rewriter = HeuristicRewriter()
    rewritten = rewriter.rewrite("Why does getUserById() throw a NullPointerException?")
    assert "getUserById" in rewritten
    assert "NullPointerException" in rewritten
    assert "does" not in rewritten.lower().split()
    assert "why" not in rewritten.lower().split()


def test_heuristic_rewriter_preserves_identifier_casing():
    rewriter = HeuristicRewriter()
    rewritten = rewriter.rewrite("What does getUserById mean?")
    assert "getUserById" in rewritten  # not lowercased


def test_heuristic_rewriter_falls_back_to_original_if_all_stopwords():
    rewriter = HeuristicRewriter()
    rewritten = rewriter.rewrite("what is it")
    assert rewritten == "what is it"


def test_llm_rewriter_refuses_to_construct_without_api_key(monkeypatch):
    monkeypatch.setattr(rewriter_mod, "ANTHROPIC_API_KEY", None)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        LLMRewriter()
