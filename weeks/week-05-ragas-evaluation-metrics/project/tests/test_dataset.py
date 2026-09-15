from app.corpus import CORPUS
from app.dataset import HAND_LABELED, generate_synthetic_samples
from tests.conftest import requires_openai

_CORPUS_IDS = {d.id for d in CORPUS}


def test_hand_labeled_has_ten_samples():
    assert len(HAND_LABELED) == 10


def test_hand_labeled_samples_reference_real_corpus_docs():
    assert all(s.source_doc_id in _CORPUS_IDS for s in HAND_LABELED)


def test_hand_labeled_samples_have_nonempty_question_and_reference():
    assert all(s.question.strip() and s.reference.strip() for s in HAND_LABELED)


def test_hand_labeled_samples_are_labeled_hand():
    assert all(s.label == "hand" for s in HAND_LABELED)


@requires_openai
def test_generate_synthetic_samples_produces_valid_samples():
    # n=2 to keep this test's API cost minimal -- full 50-sample generation is a
    # deliberate manual run via runner.py (INCLUDE_SYNTHETIC=1), not part of the
    # regular test suite.
    samples = generate_synthetic_samples(n=2)
    assert len(samples) == 2
    for s in samples:
        assert s.label == "synthetic"
        assert s.source_doc_id in _CORPUS_IDS
        assert s.question.strip() and s.reference.strip()
