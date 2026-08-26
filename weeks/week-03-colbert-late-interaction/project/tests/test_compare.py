"""app.compare's _hits() helper -- pure, no model, no index. Checks that
'did this query's expected articles show up in the top-k results' counting
logic is correct, independent of whether ColBERT or the bi-encoder produced
those results."""

from app.compare import _hits


def test_hits_counts_matching_document_ids():
    results = [
        {"document_id": "Studio Ghibli"},
        {"document_id": "Sourdough"},
        {"document_id": "Hayao Miyazaki"},
    ]
    relevant_titles = {"Studio Ghibli", "Hayao Miyazaki", "Isao Takahata"}

    assert _hits(results, relevant_titles) == 2


def test_hits_is_zero_when_nothing_relevant_appears():
    results = [{"document_id": "Sourdough"}, {"document_id": "Great Barrier Reef"}]
    relevant_titles = {"Studio Ghibli"}

    assert _hits(results, relevant_titles) == 0


def test_hits_does_not_double_count_repeated_document_ids():
    # Multiple passages from the same article can each land in the top-k --
    # _hits counts result *rows*, not unique articles, so this should be 2,
    # not 1. Worth locking in explicitly since it's easy to assume the
    # opposite.
    results = [{"document_id": "Studio Ghibli"}, {"document_id": "Studio Ghibli"}]
    relevant_titles = {"Studio Ghibli"}

    assert _hits(results, relevant_titles) == 2


def test_hits_handles_empty_results():
    assert _hits([], {"Studio Ghibli"}) == 0
