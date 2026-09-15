"""Resolves the 6 RAGAS metrics this week's task names, against whichever API shape
the installed `ragas` version actually exposes. RAGAS's metric module/class names have
moved more than once (see concept.md's Common Pitfalls and resources.md's migration
guide link) -- 'Answer Relevancy' alone has been a lowercase `ragas.metrics` instance,
a `ResponseRelevancy` class, and is currently `AnswerRelevancy` under
`ragas.metrics.collections`. Hardcoding one import shape means a routine `ragas`
version bump silently breaks this project; this module tries the current shape first
and falls back, so an upgrade either keeps working or fails with a clear error instead
of a confusing ImportError deep in a metric class.
"""

from __future__ import annotations

from app.config import OPENAI_EMBEDDING_MODEL, OPENAI_MODEL


def resolve_metrics():
    """Returns (metrics, api_version): 6 RAGAS metric instances -- Faithfulness,
    Answer Relevancy, Context Precision, Context Recall, Semantic/Answer Similarity,
    Answer Correctness -- and which API shape produced them ("collections" or
    "legacy"). Requires OPENAI_API_KEY (checked by callers via app.llm.openai_available
    before this is invoked)."""
    try:
        return _resolve_collections_api(), "collections"
    except ImportError:
        return _resolve_legacy_api(), "legacy"


def _resolve_collections_api():
    from openai import AsyncOpenAI
    from ragas.embeddings import embedding_factory
    from ragas.llms import llm_factory
    from ragas.metrics.collections import (
        AnswerCorrectness,
        ContextPrecision,
        ContextRecall,
        Faithfulness,
        SemanticSimilarity,
    )

    try:
        from ragas.metrics.collections import AnswerRelevancy
    except ImportError:
        from ragas.metrics.collections import ResponseRelevancy as AnswerRelevancy

    llm = llm_factory(OPENAI_MODEL, client=AsyncOpenAI())
    # All 6 metrics are scored via each metric's async .ascore() (app.evaluate scores
    # "collections"-API metrics per-sample, not through ragas.evaluate()). AnswerRelevancy
    # and AnswerCorrectness call embeddings.aembed_text() internally, which raises
    # TypeError against a sync client -- so this needs an async client throughout, same
    # as the LLM judge above. SemanticSimilarity's embed_text() supports async clients
    # too (it dispatches to the running loop), so one async client covers all 3.
    embeddings = embedding_factory(
        "openai", model=OPENAI_EMBEDDING_MODEL, client=AsyncOpenAI(), interface="modern"
    )

    return [
        Faithfulness(llm=llm),
        AnswerRelevancy(llm=llm, embeddings=embeddings),
        ContextPrecision(llm=llm),
        ContextRecall(llm=llm),
        SemanticSimilarity(embeddings=embeddings),
        AnswerCorrectness(llm=llm, embeddings=embeddings),
    ]


def _resolve_legacy_api():
    """Pre-v0.4 ragas: metrics are module-level instances scored via ragas.evaluate()
    on a datasets.Dataset, not per-instance .ascore()."""
    from ragas.metrics import (
        answer_correctness,
        answer_relevancy,
        answer_similarity,
        context_precision,
        context_recall,
        faithfulness,
    )

    return [
        faithfulness,
        answer_relevancy,
        context_precision,
        context_recall,
        answer_similarity,
        answer_correctness,
    ]
