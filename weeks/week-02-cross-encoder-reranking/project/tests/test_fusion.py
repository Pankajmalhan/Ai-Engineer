import pytest

from app.fusion import rrf_fuse


def test_worked_example_from_concept_doc():
    # doc A: dense rank 1, sparse rank 3
    # doc B: dense rank 2, absent from sparse top-3
    # doc C: dense rank 3, sparse rank 1
    dense = [1, 2, 3]  # A, B, C
    sparse = [3, 4, 1]  # C, (unseen doc 4), A -> A is rank 3 in sparse

    fused = rrf_fuse([dense, sparse], k=60)
    scores = dict(fused)

    assert scores[1] == pytest.approx(1 / 61 + 1 / 63)
    assert scores[3] == pytest.approx(1 / 63 + 1 / 61)
    assert scores[2] == pytest.approx(1 / 62)
    # A and C tie, and both outrank B despite neither being #1 in both lists
    assert scores[1] == scores[3] > scores[2]


def test_document_absent_from_a_list_contributes_zero_not_a_penalty():
    dense = [10, 20]
    sparse = []  # doc 10 never appears in the sparse list at all

    fused = rrf_fuse([dense, sparse], k=60)
    scores = dict(fused)

    assert scores[10] == pytest.approx(1 / 61)


def test_top_k_truncates_the_fused_ranking():
    dense = [1, 2, 3, 4, 5]
    sparse = [5, 4, 3, 2, 1]

    fused = rrf_fuse([dense, sparse], k=60, top_k=2)

    assert len(fused) == 2


def test_larger_k_flattens_the_ranking_gap_between_top_and_later_ranks():
    ranked_list = [1, 2]

    gap_small_k = dict(rrf_fuse([ranked_list], k=1))
    gap_large_k = dict(rrf_fuse([ranked_list], k=1000))

    small_k_ratio = gap_small_k[1] / gap_small_k[2]
    large_k_ratio = gap_large_k[1] / gap_large_k[2]

    assert small_k_ratio > large_k_ratio > 1.0
