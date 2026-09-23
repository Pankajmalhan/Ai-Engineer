"""Braintrust eval file -- discovered and run by `npx braintrust eval evals/` locally,
or by the braintrustdata/eval-action in .github/workflows/week-08-braintrust-eval.yml on
every PR. Each run logs a new *experiment* under the northwind-rag-week8 project;
Braintrust diffs it against the previous experiment from the base branch, and the
eval-action posts that score delta as a PR comment -- the actual "release gate"
mechanic is Braintrust's own experiment-diffing, not something this repo scripts by hand.

Two scorers, deliberately mixed cost:
- retrieval_hit: free, deterministic -- does BM25 retrieve the one document this
  question's answer actually depends on? Ground truth (source_doc_id) is known here,
  unlike app/tracing.py's production-side retrieval_hit_rate proxy.
- faithfulness: RAGAS's LLM-judged Faithfulness metric -- does the generated answer
  only state things supported by retrieved context? Costs one OpenAI call per case
  (needs OPENAI_API_KEY, set as a repo secret for CI) and is non-deterministic between
  runs -- the same cost/determinism tradeoff Week 7 flagged for its dynamic red-team
  tier, accepted here because this is the release gate, not a cheap push-time check.
"""

from __future__ import annotations

from braintrust import Eval

from app.dataset import GOLDENS
from app.metrics import score_faithfulness
from app.pipeline import RAGPipeline

_pipeline = RAGPipeline()


def answer_question(input: str) -> dict:
    result = _pipeline.answer(input)
    return {
        "answer": result.answer,
        "contexts": result.retrieved_contexts,
        "retrieved_doc_ids": result.retrieved_doc_ids,
    }


def retrieval_hit(input, output, expected, metadata=None, **kwargs) -> dict:
    source_doc_id = (metadata or {}).get("source_doc_id")
    hit = bool(source_doc_id) and source_doc_id in output.get("retrieved_doc_ids", [])
    return {"name": "retrieval_hit", "score": 1.0 if hit else 0.0}


def faithfulness(input, output, expected, metadata=None, **kwargs) -> dict:
    score = score_faithfulness(input, output["answer"], output["contexts"])
    return {"name": "faithfulness", "score": score}


Eval(
    "northwind-rag-week8",
    data=lambda: [
        {
            "input": sample.question,
            "expected": sample.reference,
            "metadata": {"source_doc_id": sample.source_doc_id},
        }
        for sample in GOLDENS
    ],
    task=answer_question,
    scores=[retrieval_hit, faithfulness],
)
