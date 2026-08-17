import math

from app.metrics import ndcg_at_k, recall_at_k


def test_recall_hit_within_k():
    retrieved = ["a", "b", "target", "c"]
    assert recall_at_k(retrieved, "target", k=10) == 1


def test_recall_miss_outside_k():
    retrieved = ["a"] * 10 + ["target"]
    assert recall_at_k(retrieved, "target", k=10) == 0


def test_recall_miss_entirely():
    retrieved = ["a", "b", "c"]
    assert recall_at_k(retrieved, "target", k=10) == 0


def test_ndcg_perfect_ranking_scores_one():
    # single relevant chunk, retrieved first -> perfect NDCG
    retrieved = ["target", "a", "b"]
    assert ndcg_at_k(retrieved, "target", relevant_chunk_count=1, k=10) == 1.0


def test_ndcg_penalizes_lower_rank():
    first = ndcg_at_k(["target", "a", "b"], "target", relevant_chunk_count=1, k=10)
    third = ndcg_at_k(["a", "b", "target"], "target", relevant_chunk_count=1, k=10)
    assert first > third
    assert third == 1.0 / math.log2(4)  # rank 3 -> position 3, log2(3+1)


def test_ndcg_zero_when_never_retrieved():
    retrieved = ["a", "b", "c"]
    assert ndcg_at_k(retrieved, "target", relevant_chunk_count=1, k=10) == 0.0


def test_ndcg_ideal_ranking_with_multiple_relevant_chunks():
    # doc has 3 relevant chunks; retrieving all 3 first is the ideal ranking
    retrieved = ["target", "target", "target", "other", "other"]
    assert ndcg_at_k(retrieved, "target", relevant_chunk_count=3, k=10) == 1.0


def test_ndcg_caps_ideal_count_at_k():
    # doc has 20 relevant chunks but k=5 -- ideal is only the first 5, not 20
    retrieved = ["target"] * 5
    score = ndcg_at_k(retrieved, "target", relevant_chunk_count=20, k=5)
    assert score == 1.0
