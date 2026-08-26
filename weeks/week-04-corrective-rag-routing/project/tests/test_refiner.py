import pytest

import app.refiner as refiner_mod
from app.refiner import HeuristicRefiner, LLMRefiner


def test_heuristic_refiner_keeps_most_relevant_sentence():
    refiner = HeuristicRefiner(max_bullets=2)
    texts = [
        "Our refund policy allows full refunds within 30 days of purchase. "
        "We also offer store credit as an alternative. "
        "The office closes at 5pm on weekdays."
    ]
    bullets = refiner.refine("What is the refund policy?", texts)
    assert any("refund" in b.lower() for b in bullets)
    assert len(bullets) <= 2


def test_heuristic_refiner_respects_max_bullets():
    refiner = HeuristicRefiner(max_bullets=1)
    texts = ["Sentence one about refunds. Sentence two about refunds too."]
    bullets = refiner.refine("refunds", texts)
    assert len(bullets) == 1


def test_heuristic_refiner_handles_multiple_texts():
    refiner = HeuristicRefiner(max_bullets=3)
    texts = ["Refund policy is 30 days.", "Unrelated holiday schedule information."]
    bullets = refiner.refine("refund policy", texts)
    assert bullets[0] == "Refund policy is 30 days."


def test_heuristic_refiner_empty_input_returns_empty():
    refiner = HeuristicRefiner()
    assert refiner.refine("anything", []) == []


def test_llm_refiner_refuses_to_construct_without_api_key(monkeypatch):
    monkeypatch.setattr(refiner_mod, "ANTHROPIC_API_KEY", None)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        LLMRefiner()
