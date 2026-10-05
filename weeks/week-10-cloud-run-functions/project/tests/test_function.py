"""Exercises the deployed function's exact entry point (`main.rag_chat`) through
functions-framework's own test harness -- not a hand-rolled Flask app -- so this test
would catch a broken `--function` target before it ever reaches `gcloud run deploy`.
"""

from __future__ import annotations

import functions_framework
from app.llm import GenerationResult
from app.pipeline import RAGPipeline


def _make_client(monkeypatch):
    def _fake_generate(question: str, contexts: list[str]) -> GenerationResult:
        return GenerationResult(answer=f"stub answer for: {question}", input_tokens=1, output_tokens=1)

    monkeypatch.setattr("app.pipeline.generate_answer", _fake_generate)
    monkeypatch.setattr("main._pipeline", RAGPipeline())

    import main

    app = functions_framework.create_app(target="rag_chat", source=main.__file__)
    return app.test_client()


def test_health_check_is_a_plain_get(monkeypatch):
    client = _make_client(monkeypatch)
    response = client.get("/")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_missing_question_is_a_400(monkeypatch):
    client = _make_client(monkeypatch)
    response = client.post("/", json={})
    assert response.status_code == 400


def test_chat_returns_answer_and_contexts(monkeypatch):
    client = _make_client(monkeypatch)
    response = client.post("/", json={"question": "What's the refund window for annual plans?"})
    assert response.status_code == 200
    body = response.get_json()
    assert body["answer"].startswith("stub answer for:")
    assert body["retrieved_contexts"]
    assert body["retrieved_doc_ids"]


def test_function_traces_and_flushes_when_langfuse_is_configured(monkeypatch):
    """The deployed entry point itself must go through app/tracing.py: with credentials set,
    one request yields a request_error=0 score and exactly one flush before the response."""
    import sys
    import types
    from contextlib import contextmanager

    seen = {"scores": [], "flushes": 0, "tags": []}

    class Obs:
        trace_id = "t"

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def start_as_current_observation(self, **kw):
            return Obs()

        def update(self, **kw):
            pass

    class Client:
        def start_as_current_observation(self, **kw):
            return Obs()

        def create_score(self, **kw):
            seen["scores"].append(kw["name"] + "=" + str(kw["value"]))

        def flush(self):
            seen["flushes"] += 1

    @contextmanager
    def propagate_attributes(**kw):
        seen["tags"].append(kw["tags"])
        yield

    module = types.ModuleType("langfuse")
    module.get_client = lambda: Client()
    module.propagate_attributes = propagate_attributes
    monkeypatch.setitem(sys.modules, "langfuse", module)
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    monkeypatch.setenv("DEPLOY_TARGET", "cloud-run-function")
    monkeypatch.setattr(
        "app.tracing.generate_answer",
        lambda q, c: GenerationResult(answer="ok", input_tokens=1, output_tokens=1),
    )

    client = _make_client(monkeypatch)
    response = client.post("/", json={"question": "What's the refund window for annual plans?"})

    assert response.status_code == 200
    assert "request_error=0" in seen["scores"]
    assert seen["flushes"] == 1
    assert seen["tags"] == [["cloud-run-function"]]
