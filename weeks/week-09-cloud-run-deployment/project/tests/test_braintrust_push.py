import pytest

from app import braintrust_push
from app.dataset import GOLDENS


def test_braintrust_available_false_without_key(monkeypatch):
    monkeypatch.delenv("BRAINTRUST_API_KEY", raising=False)
    assert braintrust_push.braintrust_available() is False


def test_braintrust_available_true_with_key(monkeypatch):
    monkeypatch.setenv("BRAINTRUST_API_KEY", "sk-test")
    assert braintrust_push.braintrust_available() is True


def test_push_dataset_raises_clearly_without_key(monkeypatch):
    monkeypatch.delenv("BRAINTRUST_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="BRAINTRUST_API_KEY"):
        braintrust_push.push_dataset()


def test_push_dataset_inserts_one_row_per_golden(monkeypatch):
    monkeypatch.setenv("BRAINTRUST_API_KEY", "sk-test")

    inserted = []

    class FakeDataset:
        def insert(self, input, expected, metadata):
            inserted.append({"input": input, "expected": expected, "metadata": metadata})

        def flush(self):
            pass

    monkeypatch.setattr("braintrust.init_dataset", lambda project, name: FakeDataset())

    count = braintrust_push.push_dataset()

    assert count == len(GOLDENS)
    assert len(inserted) == len(GOLDENS)
    assert inserted[0]["input"] == GOLDENS[0].question
    assert inserted[0]["expected"] == GOLDENS[0].reference
    assert inserted[0]["metadata"] == {"source_doc_id": GOLDENS[0].source_doc_id}
