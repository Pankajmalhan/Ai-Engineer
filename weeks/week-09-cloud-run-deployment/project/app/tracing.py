"""Langfuse instrumentation for the RAG endpoint. THIS FILE IS IDENTICAL IN WEEK 9's
Cloud Run service (app/tracing.py) AND WEEK 10's Cloud Run function
(function/app/tracing.py): each deployment builds into its own container, so each carries a
copy, and Week 12's tests/test_tracing_parity.py fails if the two ever drift apart.

What every request produces in Langfuse:
  - a trace with nested retrieval / generation observations, token usage and cost
  - a `retrieval_hit_rate` BOOLEAN score (a ground-truth-free proxy, see below)
  - a `request_error` BOOLEAN score: 1 if the request raised, 0 if it succeeded. A boolean
    score's average is the *share* that are true, so "avg(request_error) > 0.02 over 1 hour"
    IS the "error rate above 2%" alert -- Langfuse alerts evaluate one metric, not a ratio
    of two counts, so the rate has to exist as a score first.
  - the deployment target as a tag and in metadata (DEPLOY_TARGET env var, e.g.
    `cloud-run-service` / `cloud-run-function`), and as Langfuse's `environment`
    (LANGFUSE_TRACING_ENVIRONMENT, read by the SDK) so alerts and dashboards can be filtered
    per deployment.

Three production rules this module enforces:
  1. Telemetry must never take the app down. A Langfuse failure (client construction, scoring,
     flushing) is logged and swallowed; a failure of the REQUEST itself is recorded and
     re-raised unchanged.
  2. Serverless instances are frozen between requests (Cloud Run throttles CPU when no
     request is in flight), so Langfuse's background exporter may never get to run. Spans
     and scores are therefore flushed at the end of each request (LANGFUSE_FLUSH_ON_REQUEST,
     default on; the cost is one short network call per request).
  3. No credentials -> no Langfuse: langfuse_enabled() gates every call site, so tests and
     local runs without LANGFUSE_* env vars never try to reach a Langfuse server.

`retrieval_hit_rate` is a ground-truth-free proxy: production requests have no labeled
"correct" document, so a request counts as a "hit" when BM25's top score clears
MIN_RELEVANCE_SCORE (retrieval found something it is confident about), not when the *right*
document was retrieved -- that stronger version is only computable offline against a labeled
set (see Week 8's evals/eval_rag_quality.py).
"""

from __future__ import annotations

import logging
import os

from app.llm import generate_answer
from app.pipeline import PipelineResult, RAGPipeline

logger = logging.getLogger(__name__)

MIN_RELEVANCE_SCORE = float(os.environ.get("RETRIEVAL_MIN_RELEVANCE_SCORE", "0.5"))

# Rough $/token pricing for gpt-4o-mini, used only to populate Langfuse's cost display.
# Update if OPENAI_MODEL changes, or omit cost_details and let Langfuse infer cost from
# its own model price table instead of hardcoding it here.
_INPUT_COST_PER_TOKEN = 0.15 / 1_000_000
_OUTPUT_COST_PER_TOKEN = 0.60 / 1_000_000


def langfuse_enabled() -> bool:
    return bool(os.environ.get("LANGFUSE_PUBLIC_KEY")) and bool(os.environ.get("LANGFUSE_SECRET_KEY"))


def deploy_target() -> str:
    return os.environ.get("DEPLOY_TARGET", "local")


def flush_on_request() -> bool:
    return os.environ.get("LANGFUSE_FLUSH_ON_REQUEST", "true").strip().lower() != "false"


def _safe(action: str, fn, *args, **kwargs) -> None:
    """Runs a telemetry call; logs and swallows any failure (rule 1)."""
    try:
        fn(*args, **kwargs)
    except Exception:
        logger.warning("langfuse %s failed; continuing without it", action, exc_info=True)


def traced_answer(pipeline: RAGPipeline, question: str) -> PipelineResult:
    """Runs one request through the pipeline. With Langfuse credentials configured, wraps it
    in a trace (see module docstring); otherwise falls straight through to the plain
    pipeline, unmodified.
    """
    if not langfuse_enabled():
        return pipeline.answer(question)

    try:
        from langfuse import get_client, propagate_attributes

        langfuse = get_client()
    except Exception:
        logger.warning("langfuse unavailable; serving this request untraced", exc_info=True)
        return pipeline.answer(question)

    try:
        return _traced(langfuse, propagate_attributes, pipeline, question)
    finally:
        if flush_on_request():
            _safe("flush", langfuse.flush)


def _traced(langfuse, propagate_attributes, pipeline: RAGPipeline, question: str) -> PipelineResult:
    target = deploy_target()

    with langfuse.start_as_current_observation(
        as_type="span", name="rag-request", input={"question": question}
    ) as trace:
        with propagate_attributes(tags=[target], metadata={"deploy_target": target}):
            try:
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
                    try:
                        result = generate_answer(question, contexts)
                    except Exception as exc:
                        generation.update(level="ERROR", status_message=f"{type(exc).__name__}: {exc}")
                        raise

                    generation.update(
                        output=result.answer,
                        usage_details={"input": result.input_tokens, "output": result.output_tokens},
                        cost_details={
                            "input": result.input_tokens * _INPUT_COST_PER_TOKEN,
                            "output": result.output_tokens * _OUTPUT_COST_PER_TOKEN,
                        },
                    )
            except Exception as exc:
                message = f"{type(exc).__name__}: {exc}"
                _safe("trace error update", trace.update, level="ERROR", status_message=message)
                _safe(
                    "request_error score",
                    langfuse.create_score,
                    trace_id=trace.trace_id,
                    name="request_error",
                    value=1,
                    data_type="BOOLEAN",
                    comment=message[:200],
                )
                raise

            _safe("trace update", trace.update, output={"answer": result.answer})
            _safe(
                "retrieval_hit_rate score",
                langfuse.create_score,
                trace_id=trace.trace_id,
                name="retrieval_hit_rate",
                value=1 if top_score >= MIN_RELEVANCE_SCORE else 0,
                data_type="BOOLEAN",
                comment=f"top BM25 score {top_score:.3f} vs threshold {MIN_RELEVANCE_SCORE}",
            )
            _safe(
                "request_error score",
                langfuse.create_score,
                trace_id=trace.trace_id,
                name="request_error",
                value=0,
                data_type="BOOLEAN",
            )

    return PipelineResult(
        question=question,
        answer=result.answer,
        retrieved_contexts=contexts,
        retrieved_doc_ids=[d.id for d in docs],
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )
