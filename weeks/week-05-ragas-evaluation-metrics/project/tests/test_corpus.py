from app.corpus import CORPUS


def test_corpus_has_ten_documents():
    assert len(CORPUS) == 10


def test_corpus_ids_are_unique():
    ids = [d.id for d in CORPUS]
    assert len(ids) == len(set(ids))


def test_corpus_documents_have_nonempty_text():
    assert all(len(d.text) > 20 for d in CORPUS)
