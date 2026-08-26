import pytest

import app.answerer as answerer_mod
from app.answerer import ExtractiveAnswerer, LLMAnswerer


def test_extractive_answerer_formats_bullets():
    answerer = ExtractiveAnswerer()
    result = answerer.answer("what's the refund policy?", ["Refunds within 30 days.", "Prorated after that."])
    assert "Refunds within 30 days." in result
    assert "Prorated after that." in result
    assert "[extractive" in result  # clearly labeled as non-generative


def test_extractive_answerer_handles_no_context():
    answerer = ExtractiveAnswerer()
    result = answerer.answer("anything", [])
    assert "No relevant context" in result


def test_llm_answerer_refuses_to_construct_without_api_key(monkeypatch):
    monkeypatch.setattr(answerer_mod, "ANTHROPIC_API_KEY", None)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        LLMAnswerer()
