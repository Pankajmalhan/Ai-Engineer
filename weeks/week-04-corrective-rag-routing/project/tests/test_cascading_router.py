import json

import pytest

import app.router as router_mod
from app.router import CascadingRouter, LLMRouteClassifier, RouteDecision, Strategy


class FakeSemanticRouter:
    """Stands in for SemanticRouter so cascade branching can be tested without
    depending on real TF-IDF scores landing above/below a threshold by chance."""

    def __init__(self, decision: RouteDecision):
        self.decision = decision
        self.calls: list[str] = []

    def route(self, query: str) -> RouteDecision:
        self.calls.append(query)
        return self.decision


class FakeLLMClassifier:
    def __init__(self, strategy: Strategy):
        self.strategy = strategy
        self.calls: list[str] = []

    def classify(self, query: str) -> Strategy:
        self.calls.append(query)
        return self.strategy


CONFIDENT_DECISION = RouteDecision(
    strategy=Strategy.CODE, confidence=0.9,
    scores={Strategy.FACTUAL: 0.1, Strategy.CODE: 0.9, Strategy.CONVERSATIONAL: 0.0},
    used_default_fallback=False,
)

LOW_CONFIDENCE_DECISION = RouteDecision(
    strategy=Strategy.FACTUAL, confidence=0.02,
    scores={Strategy.FACTUAL: 0.1, Strategy.CODE: 0.09, Strategy.CONVERSATIONAL: 0.0},
    used_default_fallback=True,
)


def test_confident_decision_skips_llm_entirely():
    semantic = FakeSemanticRouter(CONFIDENT_DECISION)
    llm = FakeLLMClassifier(Strategy.CONVERSATIONAL)
    router = CascadingRouter(semantic_router=semantic, llm_classifier=llm)

    decision = router.route("some confident query")

    assert decision.strategy == Strategy.CODE  # untouched, from the semantic tier
    assert decision.escalated_to_llm is False
    assert llm.calls == []  # never called -- this is the whole cost-saving point
    assert router.escalation_rate == 0.0


def test_low_confidence_decision_escalates_to_llm():
    semantic = FakeSemanticRouter(LOW_CONFIDENCE_DECISION)
    llm = FakeLLMClassifier(Strategy.CODE)
    router = CascadingRouter(semantic_router=semantic, llm_classifier=llm)

    decision = router.route("some ambiguous query")

    assert decision.strategy == Strategy.CODE  # the LLM's call, not the semantic default
    assert decision.escalated_to_llm is True
    assert llm.calls == ["some ambiguous query"]
    assert router.escalation_rate == 1.0


def test_low_confidence_with_no_llm_classifier_behaves_like_bare_semantic_router():
    semantic = FakeSemanticRouter(LOW_CONFIDENCE_DECISION)
    router = CascadingRouter(semantic_router=semantic, llm_classifier=None)

    decision = router.route("some ambiguous query")

    assert decision.strategy == Strategy.FACTUAL  # the semantic tier's own default
    assert decision.escalated_to_llm is False
    assert router.escalation_rate == 0.0


def test_escalation_rate_reflects_mixed_traffic():
    semantic = FakeSemanticRouter(CONFIDENT_DECISION)
    llm = FakeLLMClassifier(Strategy.CODE)
    router = CascadingRouter(semantic_router=semantic, llm_classifier=llm)

    router.route("confident 1")
    semantic.decision = LOW_CONFIDENCE_DECISION
    router.route("ambiguous 1")
    router.route("ambiguous 2")

    assert router.total_routed == 3
    assert router.total_escalated == 2
    assert router.escalation_rate == pytest.approx(2 / 3)


def test_escalation_is_logged_as_jsonl(tmp_path):
    log_path = tmp_path / "escalations.jsonl"
    semantic = FakeSemanticRouter(LOW_CONFIDENCE_DECISION)
    llm = FakeLLMClassifier(Strategy.CODE)
    router = CascadingRouter(semantic_router=semantic, llm_classifier=llm, log_path=log_path)

    router.route("some ambiguous query")

    lines = log_path.read_text().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["query"] == "some ambiguous query"
    assert entry["llm_strategy"] == "code"
    assert entry["tfidf_scores"]["factual"] == 0.1


def test_confident_decision_never_writes_to_the_log(tmp_path):
    log_path = tmp_path / "escalations.jsonl"
    semantic = FakeSemanticRouter(CONFIDENT_DECISION)
    llm = FakeLLMClassifier(Strategy.CODE)
    router = CascadingRouter(semantic_router=semantic, llm_classifier=llm, log_path=log_path)

    router.route("some confident query")

    assert not log_path.exists()


def test_llm_route_classifier_refuses_to_construct_without_api_key(monkeypatch):
    monkeypatch.setattr(router_mod, "ANTHROPIC_API_KEY", None)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        LLMRouteClassifier()
