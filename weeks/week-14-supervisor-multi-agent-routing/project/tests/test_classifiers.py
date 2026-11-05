import pytest
from pydantic import ValidationError

from app.classifiers import SUPERVISOR_PROMPT, HeuristicClassifier, LLMClassifier
from app.schemas import Route


def test_route_rejects_unknown_category_and_out_of_range_confidence():
    with pytest.raises(ValidationError):
        Route(category="codes", confidence=0.9)
    with pytest.raises(ValidationError):
        Route(category="code", confidence=1.4)


@pytest.mark.parametrize(
    "query, category",
    [
        ("Where is the retry function implemented?", "code"),
        ("Are we allowed to skip code review?", "rules"),
        ("What is a subscription plan?", "domain"),
    ],
)
def test_heuristic_confident_on_clear_queries(query, category):
    r = HeuristicClassifier().classify(query)
    assert r.category == category
    assert r.confidence >= 0.6


def test_heuristic_low_confidence_with_no_evidence():
    r = HeuristicClassifier().classify("hmm, tell me about it")
    assert r.confidence < 0.6


def test_heuristic_low_confidence_when_evidence_is_split():
    # one code keyword, one rules keyword, one domain keyword
    r = HeuristicClassifier().classify("Is the function allowed in the billing flow?")
    assert r.confidence < 0.6


class _FakeStructuredLLM:
    """Stands in for a chat model: records the prompt, returns what with_structured_output would."""

    def __init__(self, result):
        self.result = result
        self.schema = None
        self.messages = None

    def with_structured_output(self, schema):
        self.schema = schema
        return self

    def invoke(self, messages):
        self.messages = messages
        return self.result


def test_llm_classifier_binds_route_schema_and_sends_prompt_and_query():
    llm = _FakeStructuredLLM(Route(category="rules", confidence=0.9))
    result = LLMClassifier(llm).classify("can we force-push?")
    assert llm.schema is Route
    assert llm.messages[0].content == SUPERVISOR_PROMPT
    assert llm.messages[1].content == "can we force-push?"
    assert result.category == "rules"


def test_llm_classifier_validates_dict_output():
    llm = _FakeStructuredLLM({"category": "domain", "confidence": 0.7})
    assert LLMClassifier(llm).classify("x") == Route(category="domain", confidence=0.7, reasoning="")
    with pytest.raises(ValidationError):
        LLMClassifier(_FakeStructuredLLM({"category": "nope", "confidence": 0.7})).classify("x")
