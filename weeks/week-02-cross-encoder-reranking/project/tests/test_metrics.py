import pytest

from app.metrics import ndcg_at_k, recall_at_k


def test_relevant_doc_at_rank_1_scores_perfect_ndcg():
    assert ndcg_at_k([10, 20, 30], relevant_ids={10}, k=10) == pytest.approx(1.0)


def test_relevant_doc_outside_top_k_scores_zero():
    ranked = list(range(1, 12))  # 11 docs, relevant one is 12th
    assert ndcg_at_k(ranked, relevant_ids={999}, k=10) == 0.0


def test_worked_example_single_relevant_doc_at_rank_3():
    # rel doc at rank 3: DCG = 1/log2(4); single relevant doc -> IDCG = 1/log2(2) = 1
    import math

    ranked = [1, 2, 3, 4]
    ndcg = ndcg_at_k(ranked, relevant_ids={3}, k=10)
    assert ndcg == pytest.approx(1.0 / math.log2(4))


def test_reranking_a_relevant_doc_to_rank_1_increases_ndcg_over_lower_rank():
    """This is the exact effect Stage 2 reranking is supposed to produce:
    the relevant doc was already in the pool (recall@10 was already a hit),
    reranking just moves it closer to rank 1."""
    before = ndcg_at_k([5, 6, 7, 42], relevant_ids={42}, k=10)  # rank 4
    after = ndcg_at_k([42, 5, 6, 7], relevant_ids={42}, k=10)  # rank 1
    assert after > before
    assert after == pytest.approx(1.0)


def test_multiple_relevant_docs_ideal_ordering_scores_one():
    ranked = [1, 2, 3]
    assert ndcg_at_k(ranked, relevant_ids={1, 2}, k=10) == pytest.approx(1.0)


def test_recall_at_k_is_binary_hit_or_miss():
    assert recall_at_k([1, 2, 3], relevant_ids={2}, k=10) == 1
    assert recall_at_k([1, 2, 3], relevant_ids={99}, k=10) == 0


def test_recall_at_k_respects_k_cutoff():
    assert recall_at_k([1, 2, 3, 4], relevant_ids={4}, k=2) == 0
