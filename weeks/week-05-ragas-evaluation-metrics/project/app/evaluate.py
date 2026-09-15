"""Orchestrates one full evaluation run: runs the pipeline over a set of EvalSamples
to get real responses/retrieved_contexts, builds the dataset shape RAGAS's resolved
API version expects, scores it against all 6 metrics, and reports the weakest one --
the 'identify the weakest metric, that's where you improve next' step from this
week's task.
"""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass

from app.dataset import EvalSample
from app.metrics import resolve_metrics
from app.pipeline import RAGPipeline

# Columns that describe the sample itself, not a metric score -- excluded when
# averaging result.to_pandas() into per-metric means. Deliberately not hardcoding
# metric column names since those are exactly what's moved across ragas versions.
_NON_METRIC_COLUMNS = {
    "user_input", "response", "retrieved_contexts", "reference",
    "question", "answer", "contexts", "ground_truth",
}


@dataclass
class EvaluationSummary:
    scores: dict[str, float]
    weakest_metric: str
    sample_count: int
    api_version: str


def run_evaluation(samples: list[EvalSample], pipeline: RAGPipeline | None = None) -> EvaluationSummary:
    pipeline = pipeline or RAGPipeline()
    metrics, api_version = resolve_metrics()
    print(metrics)
    print(api_version)

    results = [pipeline.answer(s.question) for s in samples]

    if api_version == "collections":
        # "collections" metrics (ragas.metrics.collections.*) aren't instances of the
        # legacy ragas.metrics.base.Metric class that ragas.evaluate() type-checks for
        # -- they're scored per-sample via .ascore(), not via evaluate()+Dataset.
        scores = _score_collections(metrics, results, samples)
    else:
        dataset = _build_dataset(results, samples)

        from ragas import evaluate

        result = evaluate(dataset=dataset, metrics=metrics)
        df = result.to_pandas()
        score_columns = [c for c in df.columns if c not in _NON_METRIC_COLUMNS]
        scores = {c: float(df[c].mean()) for c in score_columns}

    weakest_metric = min(scores, key=scores.get)

    return EvaluationSummary(
        scores=scores, weakest_metric=weakest_metric, sample_count=len(samples), api_version=api_version
    )


def _score_collections(metrics, results, samples: list[EvalSample]) -> dict[str, float]:
    """Scores "collections"-API metrics, whose .ascore() signature differs per metric
    (Faithfulness wants retrieved_contexts, SemanticSimilarity doesn't, etc.) -- inspect
    each metric's accepted params instead of hardcoding a per-metric field list, in
    keeping with this module's policy of not hardcoding ragas's shifting API shapes.
    """

    async def _run() -> dict[str, float]:
        per_metric: dict[str, list[float]] = {m.name: [] for m in metrics}
        for r, s in zip(results, samples):
            available = {
                "user_input": r.user_input,
                "response": r.response,
                "retrieved_contexts": r.retrieved_contexts,
                "reference": s.reference,
            }
            for metric in metrics:
                accepted = inspect.signature(metric.ascore).parameters
                kwargs = {k: v for k, v in available.items() if k in accepted}
                result = await metric.ascore(**kwargs)
                per_metric[metric.name].append(result.value)
        return {name: sum(values) / len(values) for name, values in per_metric.items()}

    return asyncio.run(_run())


def _build_dataset(results, samples: list[EvalSample]):
    """Builds the legacy datasets.Dataset shape ragas.evaluate() expects. Only called
    for api_version == "legacy" -- collections-API metrics are scored directly via
    _score_collections(), which doesn't go through ragas.evaluate() at all.
    """
    from datasets import Dataset

    return Dataset.from_dict(
        {
            "question": [r.user_input for r in results],
            "answer": [r.response for r in results],
            "contexts": [r.retrieved_contexts for r in results],
            "ground_truth": [s.reference for s in samples],
        }
    )
