"""app/tracing.py against a fake Langfuse client -- no server, no network, no real keys.
(This exact file is also Week 10's tests/test_tracing.py; the module under test is identical
in both deployments.)
"""

from __future__ import annotations

import sys
import types

import pytest

from app import tracing
from app.llm import GenerationResult


# ---- fake Langfuse -----------------------------------------------------------------------

class Recorder:
    def __init__(self):
        self.scores: list[dict] = []
        self.updates: list[dict] = []
        self.propagated: list[dict] = []
        self.flushes = 0
        self.root_span_names: list[str] = []


class FakeObservation:
    trace_id = "trace-123"

    def __init__(self, rec: Recorder):
        self._rec = rec

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False  # never swallows the request's exception

    def start_as_current_observation(self, **kwargs):
        return FakeObservation(self._rec)

    def update(self, **kwargs):
        self._rec.updates.append(kwargs)


class FakeClient:
    def __init__(self, rec: Recorder, flush_raises: bool = False, score_raises: bool = False):
        self._rec, self._flush_raises, self._score_raises = rec, flush_raises, score_raises

    def start_as_current_observation(self, **kwargs):
        self._rec.root_span_names.append(kwargs.get("name", ""))
        return FakeObservation(self._rec)

    def create_score(self, **kwargs):
        if self._score_raises:
            raise RuntimeError("scores endpoint down")
        self._rec.scores.append(kwargs)

    def flush(self):
        self._rec.flushes += 1
        if self._flush_raises:
            raise RuntimeError("flush failed")


@pytest.fixture
def langfuse(monkeypatch):
    """Enables tracing and installs a fake `langfuse` module. Returns the Recorder."""
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.delenv("LANGFUSE_FLUSH_ON_REQUEST", raising=False)
    monkeypatch.delenv("DEPLOY_TARGET", raising=False)
    rec = Recorder()
    install(monkeypatch, rec)
    return rec


def install(monkeypatch, rec: Recorder, **client_kwargs):
    from contextlib import contextmanager

    @contextmanager
    def propagate_attributes(**kwargs):
        rec.propagated.append(kwargs)
        yield

    module = types.ModuleType("langfuse")
    module.get_client = lambda: FakeClient(rec, **client_kwargs)
    module.propagate_attributes = propagate_attributes
    monkeypatch.setitem(sys.modules, "langfuse", module)


@pytest.fixture
def stub_generation(monkeypatch):
    monkeypatch.setattr(
        "app.tracing.generate_answer",
        lambda question, contexts: GenerationResult(
            answer=f"stub answer for: {question}", input_tokens=42, output_tokens=7
        ),
    )


def _score(rec: Recorder, name: str) -> dict:
    (match,) = [s for s in rec.scores if s["name"] == name]
    return match


QUESTION = "What's the refund window for annual plans?"


# ---- gating -------------------------------------------------------------------------------

def test_langfuse_enabled_requires_both_keys(monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    assert tracing.langfuse_enabled() is False
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    assert tracing.langfuse_enabled() is False
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    assert tracing.langfuse_enabled() is True


def test_falls_straight_through_without_credentials(monkeypatch, pipeline):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    # a langfuse import here would be a bug: make it explode
    monkeypatch.setitem(sys.modules, "langfuse", None)

    result = tracing.traced_answer(pipeline, QUESTION)

    assert result.answer.startswith("stub answer for:")
    assert "refunds" in result.retrieved_doc_ids


# ---- success path -------------------------------------------------------------------------

def test_success_records_scores_tags_and_flushes(langfuse, stub_generation, pipeline):
    result = tracing.traced_answer(pipeline, QUESTION)

    assert result.answer.startswith("stub answer for:")
    assert (result.input_tokens, result.output_tokens) == (42, 7)
    assert _score(langfuse, "retrieval_hit_rate")["value"] == 1
    err = _score(langfuse, "request_error")
    assert err["value"] == 0 and err["data_type"] == "BOOLEAN"
    assert langfuse.flushes == 1
    # generation observation got usage + cost
    gen = next(u for u in langfuse.updates if "usage_details" in u)
    assert gen["usage_details"] == {"input": 42, "output": 7}
    assert gen["cost_details"]["input"] > 0


def test_deploy_target_becomes_tag_and_metadata(langfuse, stub_generation, pipeline, monkeypatch):
    monkeypatch.setenv("DEPLOY_TARGET", "cloud-run-function")
    tracing.traced_answer(pipeline, QUESTION)
    assert langfuse.propagated == [
        {"tags": ["cloud-run-function"], "metadata": {"deploy_target": "cloud-run-function"}}
    ]


def test_deploy_target_defaults_to_local(langfuse, stub_generation, pipeline):
    tracing.traced_answer(pipeline, QUESTION)
    assert langfuse.propagated[0]["tags"] == ["local"]


# ---- error path ---------------------------------------------------------------------------

def test_request_failure_is_recorded_flushed_and_reraised(langfuse, pipeline, monkeypatch):
    def boom(question, contexts):
        raise TimeoutError("openai timed out")

    monkeypatch.setattr("app.tracing.generate_answer", boom)

    with pytest.raises(TimeoutError, match="openai timed out"):
        tracing.traced_answer(pipeline, QUESTION)

    err = _score(langfuse, "request_error")
    assert err["value"] == 1 and "TimeoutError" in err["comment"]
    assert not [s for s in langfuse.scores if s["name"] == "retrieval_hit_rate"]  # no half-scored trace
    levels = [u for u in langfuse.updates if u.get("level") == "ERROR"]
    assert len(levels) == 2  # the generation observation AND the trace
    assert all("openai timed out" in u["status_message"] for u in levels)
    assert langfuse.flushes == 1  # failed requests are exactly the ones you must not lose


# ---- flushing -----------------------------------------------------------------------------

def test_flush_can_be_disabled(langfuse, stub_generation, pipeline, monkeypatch):
    monkeypatch.setenv("LANGFUSE_FLUSH_ON_REQUEST", "false")
    tracing.traced_answer(pipeline, QUESTION)
    assert langfuse.flushes == 0


# ---- telemetry must never break the request -----------------------------------------------

def test_flush_failure_does_not_fail_the_request(monkeypatch, stub_generation, pipeline):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    rec = Recorder()
    install(monkeypatch, rec, flush_raises=True)
    result = tracing.traced_answer(pipeline, QUESTION)
    assert result.answer.startswith("stub answer for:")


def test_score_failure_does_not_fail_the_request(monkeypatch, stub_generation, pipeline):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    install(monkeypatch, Recorder(), score_raises=True)
    result = tracing.traced_answer(pipeline, QUESTION)
    assert result.answer.startswith("stub answer for:")


def test_client_construction_failure_serves_the_request_untraced(monkeypatch, pipeline):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    module = types.ModuleType("langfuse")

    def broken():
        raise RuntimeError("cannot configure exporter")

    module.get_client = broken
    module.propagate_attributes = lambda **kw: None
    monkeypatch.setitem(sys.modules, "langfuse", module)

    result = tracing.traced_answer(pipeline, QUESTION)  # pipeline.answer path (stubbed generation)
    assert result.answer.startswith("stub answer for:")
