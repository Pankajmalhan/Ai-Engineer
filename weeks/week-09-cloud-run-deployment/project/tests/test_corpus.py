from app.corpus import CORPUS


def test_corpus_ids_are_unique():
    ids = [d.id for d in CORPUS]
    assert len(ids) == len(set(ids))


def test_corpus_has_no_redteam_fixtures():
    """Week 7's poisoned/internal-only documents are deliberately not carried over --
    this week's corpus is the clean, production-shaped fixture."""
    text = " ".join(d.text for d in CORPUS).lower()
    assert "internal" not in text
    assert "injected" not in text
