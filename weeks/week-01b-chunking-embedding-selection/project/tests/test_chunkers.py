"""Uses the smallest shortlisted model (bge-small) so these stay reasonably
fast; still hits real Chonkie chunkers and a real model, not mocks -- the
point is catching real API breakage (Chonkie/transformers/sentence-transformers
version drift), not just exercising our own glue code."""

import pytest

from app.chunkers import STRATEGIES, build_chunker, chunk_document

MODEL = "BAAI/bge-small-en-v1.5"

CODE_DOC = {
    "id": "code:test:sample.py",
    "doc_type": "code",
    "content": (
        "def add(a, b):\n"
        "    '''Adds two numbers.'''\n"
        "    return a + b\n\n\n"
        "class Greeter:\n"
        "    def __init__(self, name):\n"
        "        self.name = name\n\n"
        "    def greet(self):\n"
        "        return f'Hello, {self.name}!'\n"
    ),
}

TEXT_DOC = {
    "id": "text:test:sample",
    "doc_type": "text",
    "content": (
        "The old lighthouse stood on the cliff for a hundred years. "
        "Every night its beam swept across the water, warning ships away "
        "from the rocks below.\n\n"
        "Maria had kept the light since her father passed it to her. "
        "She knew every gear and every crack in the lens by heart. "
        "It was, in a way, the only thing that had never let her down.\n\n"
        "One winter storm nearly took the tower itself. She climbed the "
        "spiral stairs anyway, certain the light had to stay on."
    ),
}


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_strategy_produces_nonempty_chunks_for_code_and_text(strategy):
    chunker = build_chunker(strategy, MODEL)
    code_chunks = chunk_document(CODE_DOC, strategy, chunker)
    text_chunks = chunk_document(TEXT_DOC, strategy, chunker)

    assert len(code_chunks) >= 1
    assert len(text_chunks) >= 1
    assert all(c.doc_id == CODE_DOC["id"] for c in code_chunks)
    assert all(c.doc_id == TEXT_DOC["id"] for c in text_chunks)
    assert all(c.text.strip() for c in code_chunks + text_chunks)


def test_late_chunking_attaches_embeddings():
    chunker = build_chunker("late_chunking", MODEL)
    chunks = chunk_document(CODE_DOC, "late_chunking", chunker)
    assert all(c.embedding is not None for c in chunks)
    assert all(len(c.embedding) > 0 for c in chunks)


def test_other_strategies_do_not_attach_embeddings():
    chunker = build_chunker("fixed_size", MODEL)
    chunks = chunk_document(CODE_DOC, "fixed_size", chunker)
    assert all(c.embedding is None for c in chunks)


def test_ast_aware_uses_code_chunker_for_code_docs():
    chunker = build_chunker("ast_aware", MODEL)
    code_chunks = chunk_document(CODE_DOC, "ast_aware", chunker)
    # a CodeChunker split should separate the function from the class
    joined = " ".join(c.text for c in code_chunks)
    assert "def add" in joined and "class Greeter" in joined
    assert len(code_chunks) >= 2
