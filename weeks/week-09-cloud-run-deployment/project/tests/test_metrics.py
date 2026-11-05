import pytest

from app import metrics


def test_score_faithfulness_uses_collections_api_when_available(monkeypatch):
    async def fake_collections(question, answer, contexts):
        return 0.87

    monkeypatch.setattr(metrics, "_score_collections", fake_collections)

    score = metrics.score_faithfulness("q", "a", ["ctx"])

    assert score == 0.87


def test_score_faithfulness_falls_back_to_legacy_api(monkeypatch):
    async def raises_import_error(question, answer, contexts):
        raise ImportError("ragas.metrics.collections not available in this version")

    async def fake_legacy(question, answer, contexts):
        return 0.42

    monkeypatch.setattr(metrics, "_score_collections", raises_import_error)
    monkeypatch.setattr(metrics, "_score_legacy", fake_legacy)

    score = metrics.score_faithfulness("q", "a", ["ctx"])

    assert score == 0.42
