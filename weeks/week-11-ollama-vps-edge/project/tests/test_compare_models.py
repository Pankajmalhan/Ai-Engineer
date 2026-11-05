import json

from app.dataset import GOLDENS
from app.llm import GenerationResult, LLMConfig
from app.pipeline import RAGPipeline
from app.retrieval import BM25Retriever
from evals import compare_models
from evals.compare_models import format_table, run_provider


def _factory_with(answers: dict[str, str], monkeypatch):
    """Provider name -> pipeline whose generation returns a fixed answer per provider."""

    def _fake(question, contexts, config=None, client=None):
        return GenerationResult(answer=answers[config.provider], input_tokens=10, output_tokens=20)

    monkeypatch.setattr("app.pipeline.generate_answer", _fake)

    def factory(provider: str) -> RAGPipeline:
        model = {"openai": "gpt-4o-mini", "ollama": "llama3.2:3b"}[provider]
        return RAGPipeline(retriever=BM25Retriever(), llm_config=LLMConfig(provider=provider, model=model))

    return factory


def test_run_provider_scores_every_golden(monkeypatch):
    factory = _factory_with({"openai": "good", "ollama": "bad"}, monkeypatch)
    seen = []

    def scorer(question, answer, contexts):
        seen.append(answer)
        return 1.0 if answer == "good" else 0.25

    cloud = run_provider("openai", GOLDENS, factory, scorer)
    edge = run_provider("ollama", GOLDENS, factory, scorer)

    assert len(cloud.cases) == len(GOLDENS)
    assert cloud.mean_faithfulness == 1.0
    assert edge.mean_faithfulness == 0.25
    assert cloud.retrieval_hit_rate == edge.retrieval_hit_rate  # retrieval is LLM-independent
    assert cloud.retrieval_hit_rate > 0.8
    assert cloud.cases[0].output_tokens == 20


def test_skip_faithfulness_leaves_score_empty(monkeypatch):
    factory = _factory_with({"openai": "x", "ollama": "x"}, monkeypatch)
    report = run_provider("ollama", GOLDENS[:2], factory, scorer=None)
    assert report.mean_faithfulness is None
    assert "n/a" in format_table([report])


def test_format_table_lists_both_providers(monkeypatch):
    factory = _factory_with({"openai": "a", "ollama": "b"}, monkeypatch)
    reports = [run_provider(p, GOLDENS[:2], factory, lambda *_: 0.5) for p in ("openai", "ollama")]
    table = format_table(reports)
    assert "gpt-4o-mini" in table and "llama3.2:3b" in table and "0.500" in table


def test_main_writes_json(monkeypatch, tmp_path, capsys):
    factory = _factory_with({"openai": "a", "ollama": "b"}, monkeypatch)
    monkeypatch.setattr(compare_models, "_default_pipeline_factory", factory)
    out = tmp_path / "r.json"
    rc = compare_models.main(["--providers", "openai", "ollama", "--skip-faithfulness", "--out", str(out)])
    assert rc == 0
    data = json.loads(out.read_text())
    assert [r["provider"] for r in data] == ["openai", "ollama"]
    assert len(data[0]["cases"]) == len(GOLDENS)


def test_parse_spec_handles_models_that_contain_colons():
    from evals.compare_models import parse_spec

    assert parse_spec("openai") == ("openai", None)
    assert parse_spec("ollama") == ("ollama", None)
    assert parse_spec("ollama:llama3.2:3b") == ("ollama", "llama3.2:3b")
    assert parse_spec("ollama:qwen2.5:14b-instruct") == ("ollama", "qwen2.5:14b-instruct")


def test_several_models_on_one_provider_become_separate_rows(monkeypatch):
    def fake(question, contexts, config=None, client=None):
        return GenerationResult(answer=config.model, input_tokens=1, output_tokens=1)

    monkeypatch.setattr("app.pipeline.generate_answer", fake)
    reports = [
        run_provider(spec, GOLDENS[:2], compare_models._default_pipeline_factory, scorer=None)
        for spec in ("ollama:llama3.2:3b", "ollama:qwen2.5:14b-instruct")
    ]
    assert [r.model for r in reports] == ["llama3.2:3b", "qwen2.5:14b-instruct"]
    assert all(r.provider == "ollama" for r in reports)


def test_extended_goldens_triple_the_set_and_keep_ground_truth():
    from app.dataset import EXTENDED_GOLDENS

    assert len(EXTENDED_GOLDENS) == 3 * len(GOLDENS)
    assert len({g.question for g in EXTENDED_GOLDENS}) == len(EXTENDED_GOLDENS)  # no duplicates
    by_doc = {g.source_doc_id: g.reference for g in GOLDENS}
    assert all(g.reference == by_doc[g.source_doc_id] for g in EXTENDED_GOLDENS)
    # every paraphrase still retrieves its source document with real BM25
    retriever = BM25Retriever()
    for g in EXTENDED_GOLDENS:
        assert g.source_doc_id in [d.id for d in retriever.retrieve(g.question, k=3)], g.question


def test_questions_flag_selects_the_extended_set(monkeypatch, tmp_path):
    seen = []

    def factory(spec):
        monkeypatch.setattr("app.pipeline.generate_answer", lambda q, c, config=None, client=None: seen.append(q) or GenerationResult("a", 1, 1))
        return RAGPipeline(retriever=BM25Retriever(), llm_config=LLMConfig(provider="ollama", model="m"))

    monkeypatch.setattr(compare_models, "_default_pipeline_factory", factory)
    compare_models.main(["--providers", "ollama", "--skip-faithfulness", "--questions", "extended"])
    assert len(seen) == 24
