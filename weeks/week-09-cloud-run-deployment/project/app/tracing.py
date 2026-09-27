"""Langfuse instrumentation for the FastAPI RAG service: wraps every request in a
trace with nested retrieval/generation spans, logs token usage/cost on the generation
span, and logs a retrieval_hit_rate score on the trace.

`retrieval_hit_rate` here is a ground-truth-free proxy: production requests have no
labeled "correct" document to check retrieval against, so a request counts as a "hit"
when BM25's top score clears MIN_RELEVANCE_SCORE (i.e. retrieval found something it's
confident about), not when the *right* document was retrieved -- that stronger,
ground-truth version of hit rate is only computable offline against a labeled set
(see evals/eval_rag_quality.py), not on live traffic.

Import-safe and network-safe without Langfuse credentials: langfuse_enabled() gates
every call site, mirroring app.llm.openai_available()'s pattern elsewhere in this
project, so tests and local runs without LANGFUSE_* env vars never try to reach a
Langfuse server.
"""

from __future__ import annotations

import os

from app.llm import generate_answer
from app.pipeline import PipelineResult, RAGPipeline

MIN_RELEVANCE_SCORE = float(os.environ.get("RETRIEVAL_MIN_RELEVANCE_SCORE", "0.5"))

# Rough $/token pricing for gpt-4o-mini, used only to populate Langfuse's cost display.
# Update if OPENAI_MODEL changes, or omit cost_details and let Langfuse infer cost from
# its own model price table instead of hardcoding it here.
_INPUT_COST_PER_TOKEN = 0.15 / 1_000_000
_OUTPUT_COST_PER_TOKEN = 0.60 / 1_000_000


def langfuse_enabled() -> bool:
    return bool(os.environ.get("LANGFUSE_PUBLIC_KEY")) and bool(os.environ.get("LANGFUSE_SECRET_KEY"))


def traced_answer(pipeline: RAGPipeline, question: str) -> PipelineResult:
    """Runs one request through the pipeline. If Langfuse credentials are configured,
    wraps it in a trace with retrieval/generation spans and a retrieval_hit_rate score;
    otherwise falls straight through to the plain pipeline, unmodified.
    """
    if not langfuse_enabled():
        return pipeline.answer(question)

    from langfuse import get_client

    langfuse = get_client()

    with langfuse.start_as_current_observation(
        as_type="span", name="rag-request", input={"question": question}
    ) as trace:
        top_score = pipeline.retriever.top_score(question)
        docs = pipeline.retriever.retrieve(question, k=pipeline.top_k)
        contexts = [d.text for d in docs]

        with trace.start_as_current_observation(
            name="retrieval",
            input={"question": question},
            output={"retrieved_doc_ids": [d.id for d in docs], "top_bm25_score": top_score},
        ):
            pass

        with trace.start_as_current_observation(
            as_type="generation",
            name="generation",
            input={"question": question, "contexts": contexts},
        ) as generation:
            result = generate_answer(question, contexts)
          
            generation.update(
                output=result.answer,
                usage_details={"input": result.input_tokens, "output": result.output_tokens},
                cost_details={
                    "input": result.input_tokens * _INPUT_COST_PER_TOKEN,
                    "output": result.output_tokens * _OUTPUT_COST_PER_TOKEN,
                },
            )

        trace.update(output={"answer": result.answer})
        langfuse.create_score(
            trace_id=trace.trace_id,
            name="retrieval_hit_rate",
            value=1 if top_score >= MIN_RELEVANCE_SCORE else 0,
            data_type="BOOLEAN",
            comment=f"top BM25 score {top_score:.3f} vs threshold {MIN_RELEVANCE_SCORE}",
        )

    return PipelineResult(
        question=question,
        answer=result.answer,
        retrieved_contexts=contexts,
        retrieved_doc_ids=[d.id for d in docs],
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )
