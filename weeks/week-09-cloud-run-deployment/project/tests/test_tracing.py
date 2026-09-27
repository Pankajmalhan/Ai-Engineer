from app import tracing


def test_langfuse_enabled_false_without_keys(monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    assert tracing.langfuse_enabled() is False


def test_langfuse_enabled_true_with_both_keys(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    assert tracing.langfuse_enabled() is True


def test_langfuse_enabled_false_with_only_one_key(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    assert tracing.langfuse_enabled() is False


def test_traced_answer_falls_through_without_credentials(monkeypatch, pipeline):
    """No LANGFUSE_* env vars set -- traced_answer must never import/call the Langfuse
    client, so this must succeed with no network access and no langfuse credentials."""
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)

    result = tracing.traced_answer(pipeline, "What's the refund window for annual plans?")

    assert result.answer.startswith("stub answer for:")
    assert "refunds" in result.retrieved_doc_ids


def test_traced_answer_uses_langfuse_client_when_enabled(monkeypatch, pipeline):
    """With credentials set, traced_answer must go through get_client()'s spans/score
    APIs -- verified here against a fake client, no real Langfuse server involved."""
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")

    # traced_answer calls generate_answer directly (not pipeline.answer()) so it can
    # wrap retrieval and generation in separate spans -- the `pipeline` fixture's
    # patch of app.pipeline.generate_answer doesn't cover that call site.
    from app.llm import GenerationResult

    monkeypatch.setattr(
        "app.tracing.generate_answer",
        lambda question, contexts: GenerationResult(
            answer=f"stub answer for: {question}", input_tokens=42, output_tokens=7
        ),
    )

    events = {"scores": [], "generation_updates": []}

    class FakeObservation:
        trace_id = "trace-123"

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def start_as_current_observation(self, **kwargs):
            return FakeObservation()

        def update(self, **kwargs):
            events["generation_updates"].append(kwargs)

    class FakeLangfuseClient:
        def start_as_current_observation(self, **kwargs):
            return FakeObservation()

        def create_score(self, **kwargs):
            events["scores"].append(kwargs)

    import sys
    import types

    fake_module = types.ModuleType("langfuse")
    fake_module.get_client = lambda: FakeLangfuseClient()
    monkeypatch.setitem(sys.modules, "langfuse", fake_module)

    result = tracing.traced_answer(pipeline, "What's the refund window for annual plans?")

    assert result.answer.startswith("stub answer for:")
    assert len(events["scores"]) == 1
    assert events["scores"][0]["name"] == "retrieval_hit_rate"
    assert events["scores"][0]["value"] == 1
