from app.corpus import CORPUS
from app.dataset import GOLDENS


def test_every_golden_source_doc_exists_in_corpus():
    corpus_ids = {d.id for d in CORPUS}
    for sample in GOLDENS:
        assert sample.source_doc_id in corpus_ids


def test_goldens_cover_every_corpus_document():
    golden_ids = {s.source_doc_id for s in GOLDENS}
    corpus_ids = {d.id for d in CORPUS}
    assert golden_ids == corpus_ids


def test_goldens_have_no_blank_fields():
    for sample in GOLDENS:
        assert sample.question.strip()
        assert sample.reference.strip()
