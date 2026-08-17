"""The six chunking strategies, all as thin wrappers over Chonkie chunkers
(the starred tool from this week's resources) plus one dispatch rule for
"AST-aware" on a mixed code+text corpus.

Every strategy is parameterized by `chunk_size=512` (tokens) and, where the
strategy needs one, the *target embedding model's own tokenizer* -- so
"512 tokens" means 512 tokens in the space of whatever model will actually
embed the chunk, not an arbitrary generic tokenizer.

AST-aware is code-specific by construction (there's no AST for prose). The
practical generalization used here: code docs get Chonkie's CodeChunker
(chunks at function/class boundaries via tree-sitter); text docs fall back
to the recursive splitter, which is the closest "respects the document's
own structure" analogue for prose (paragraph/sentence boundaries instead of
syntax-tree boundaries). This is a deliberate, documented choice -- see
concept.md's "Common pitfalls" for why silently applying CodeChunker to
prose (or vice versa) would be wrong.
"""

from dataclasses import dataclass
from functools import lru_cache

from chonkie import (
    CodeChunker,
    LateChunker,
    RecursiveChunker,
    SemanticChunker,
    SentenceChunker,
    TokenChunker,
)
from transformers import AutoTokenizer

CHUNK_SIZE = 512
STRATEGIES = [
    "fixed_size",
    "sentence_window",
    "recursive",
    "semantic",
    "ast_aware",
    "late_chunking",
]

# Models that need `trust_remote_code=True` to load their custom modeling
# code. (jina-embeddings-v2's ALiBi implementation was tried first here --
# see concept.md's "Common pitfalls" -- but its HF remote code imports
# transformers internals removed in this project's transformers version,
# so the long-context slot uses nomic's ModernBERT-based model instead,
# which needs no remote code at all.)
TRUST_REMOTE_CODE_MODELS: set[str] = set()


@dataclass
class Chunk:
    text: str
    doc_id: str
    doc_type: str
    # Only late_chunking populates this: Chonkie's LateChunker computes chunk
    # embeddings as part of chunking (mean-pooled from the whole document's
    # token embeddings), so there's no separate embedding pass for it -- see
    # retrieval.py's build_index(), which uses this instead of re-embedding.
    embedding: list[float] | None = None


@lru_cache(maxsize=8)
def _hf_tokenizer(model_name: str):
    return AutoTokenizer.from_pretrained(model_name)


def _st_kwargs(model_name: str) -> dict:
    return {"trust_remote_code": True} if model_name in TRUST_REMOTE_CODE_MODELS else {}


def build_chunker(strategy: str, model_name: str, chunk_size: int = CHUNK_SIZE):
    """Returns the Chonkie chunker for `strategy`, tied to `model_name`'s
    tokenizer/embedding space. For "ast_aware", returns a (code_chunker,
    text_fallback_chunker) pair instead -- see chunk_document()."""
    tokenizer = _hf_tokenizer(model_name)

    if strategy == "fixed_size":
        return TokenChunker(tokenizer=tokenizer, chunk_size=chunk_size)
    if strategy == "sentence_window":
        return SentenceChunker(
            tokenizer=tokenizer, chunk_size=chunk_size, chunk_overlap=64
        )
    if strategy == "recursive":
        return RecursiveChunker(tokenizer=tokenizer, chunk_size=chunk_size)
    if strategy == "semantic":
        # min_sentences=3 is a deliberate floor, not a default left alone:
        # unconstrained (min_sentences=1) "auto"-threshold splitting on this
        # corpus's narrative prose was producing near-sentence-level chunks
        # (hundreds per chapter) -- a real, measured finding about semantic
        # chunking on dialogue-heavy fiction, documented in concept.md, but
        # not a fair or representative "semantic chunking" configuration to
        # benchmark against the other five strategies' much coarser output.
        return SemanticChunker(
            embedding_model=model_name,
            chunk_size=chunk_size,
            min_sentences=3,
            **_st_kwargs(model_name),
        )
    if strategy == "ast_aware":
        code_chunker = CodeChunker(language="python", chunk_size=chunk_size)
        text_fallback = RecursiveChunker(tokenizer=tokenizer, chunk_size=chunk_size)
        return (code_chunker, text_fallback)
    if strategy == "late_chunking":
        return LateChunker(
            embedding_model=model_name,
            chunk_size=chunk_size,
            **_st_kwargs(model_name),
        )
    raise ValueError(f"unknown strategy: {strategy}")


def chunk_document(doc: dict, strategy: str, chunker) -> list[Chunk]:
    """Applies an already-built chunker (from build_chunker) to one corpus
    document, returning Chunk objects tagged with the doc they came from
    (chunk-level results are always evaluated back at doc granularity)."""
    if strategy == "ast_aware":
        code_chunker, text_fallback = chunker
        active = code_chunker if doc["doc_type"] == "code" else text_fallback
        raw_chunks = active.chunk(doc["content"])
    else:
        raw_chunks = chunker.chunk(doc["content"])

    return [
        Chunk(
            text=c.text,
            doc_id=doc["id"],
            doc_type=doc["doc_type"],
            embedding=(
                list(c.embedding)
                if strategy == "late_chunking" and getattr(c, "embedding", None) is not None
                else None
            ),
        )
        for c in raw_chunks
        if c.text.strip()
    ]


def chunk_corpus(docs: list[dict], strategy: str, model_name: str) -> list[Chunk]:
    chunker = build_chunker(strategy, model_name)
    chunks: list[Chunk] = []
    for doc in docs:
        chunks.extend(chunk_document(doc, strategy, chunker))
    return chunks
