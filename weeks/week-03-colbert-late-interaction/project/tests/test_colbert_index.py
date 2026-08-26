"""Real, end-to-end ColBERT/PLAID round trip: build a tiny index from a
handful of toy sentences with the actual `colbert-ir/colbertv2.0`
checkpoint (not mocked -- same philosophy as Week 2's BGEReranker test),
and confirm MaxSim ranks the genuinely relevant sentence first.

This is intentionally toy-scale (3 short sentences, not the full Wikipedia
corpus) so it runs as part of a normal `pytest` invocation in well under a
minute -- see project/README.md for the full-corpus build (`app/index.py`),
which is a separate, slower, manually-triggered step.
"""

from pathlib import Path

import pytest

TOY_DOCS = [
    "Hayao Miyazaki co-founded Studio Ghibli with Isao Takahata in 1985.",
    "Sourdough bread needs a highly active starter and a long, cold overnight proof.",
    "Joe Hisaishi composed the music for Kiki's Delivery Service.",
]
TOY_IDS = ["ghibli", "bread", "hisaishi"]


@pytest.fixture(scope="module")
def toy_index(tmp_path_factory):
    from ragatouille import RAGPretrainedModel

    index_root = tmp_path_factory.mktemp("colbert_test_index")
    RAG = RAGPretrainedModel.from_pretrained("colbert-ir/colbertv2.0", index_root=str(index_root))
    RAG.index(
        index_name="pytest_toy_index",
        collection=TOY_DOCS,
        document_ids=TOY_IDS,
        split_documents=False,
    )
    return RAG


def test_maxsim_ranks_the_genuinely_relevant_passage_first(toy_index):
    results = toy_index.search("who founded Studio Ghibli", k=3)

    assert results[0]["document_id"] == "ghibli"
    assert results[0]["rank"] == 1
    # MaxSim is a sum over query tokens, not a bounded [-1, 1] cosine value
    # -- see concept.md -- so all we assert is a real, distinguishing gap
    # between the correct passage and the unrelated one, not a specific range.
    assert results[0]["score"] > results[-1]["score"]


def test_maxsim_score_is_not_a_bounded_cosine_value(toy_index):
    results = toy_index.search("who founded Studio Ghibli", k=1)
    # A cosine similarity is capped at 1.0; MaxSim sums one best-match per
    # query token, so a real multi-token query comfortably exceeds that.
    assert results[0]["score"] > 1.0


def test_index_stores_one_passage_per_document_when_not_split(toy_index):
    pid_docid_map_path = Path(toy_index.model.index_path) / "pid_docid_map.json"
    import json

    pid_docid_map = json.loads(pid_docid_map_path.read_text())
    assert len(pid_docid_map) == len(TOY_DOCS)
    assert set(pid_docid_map.values()) == set(TOY_IDS)
