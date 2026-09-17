"""Standalone debug script, same role as Week 5's runner.py: runs the pipeline + all
three DeepEval metrics over the golden set, prints per-metric averages against this
week's thresholds, and logs the run to W&B. Unlike tests/test_rag_quality.py, this
doesn't fail/exit nonzero on a threshold miss -- it's for eyeballing scores, not gating.

Needs OPENAI_API_KEY (real cost: pipeline generation + DeepEval's LLM-judged metrics).

Run with:            uv run python runner.py
Break retrieval too:  BREAK_RETRIEVAL=1 uv run python runner.py
"""

from app.config import (
    ANSWER_RELEVANCY_THRESHOLD,
    BREAK_RETRIEVAL,
    CONTEXT_RECALL_THRESHOLD,
    DEEPEVAL_MODEL,
    FAITHFULNESS_THRESHOLD,
)
from app.deepeval_cases import build_test_cases
from app.llm import openai_available
from app.wandb_logging import log_eval_run

_THRESHOLDS = {
    "faithfulness": FAITHFULNESS_THRESHOLD,
    "answer_relevancy": ANSWER_RELEVANCY_THRESHOLD,
    "contextual_recall": CONTEXT_RECALL_THRESHOLD,
}


def main() -> None:
    if not openai_available():
        print(
            "OPENAI_API_KEY is not set -- this project needs a real OpenAI key for "
            "pipeline generation and DeepEval's LLM-judged metrics. Set it and re-run:\n"
            "  export OPENAI_API_KEY=sk-...\n"
            "  uv run python runner.py"
        )
        return

    from deepeval.metrics import AnswerRelevancyMetric, ContextualRecallMetric, FaithfulnessMetric

    print(f"BREAK_RETRIEVAL={'on -- retrieval is intentionally reversed' if BREAK_RETRIEVAL else 'off'}")
    test_cases = build_test_cases()
    print(f"Evaluating {len(test_cases)} golden(s) against DEEPEVAL_MODEL={DEEPEVAL_MODEL}...\n")

    metrics = {
        "faithfulness": FaithfulnessMetric(threshold=FAITHFULNESS_THRESHOLD, model=DEEPEVAL_MODEL),
        "answer_relevancy": AnswerRelevancyMetric(threshold=ANSWER_RELEVANCY_THRESHOLD, model=DEEPEVAL_MODEL),
        "contextual_recall": ContextualRecallMetric(threshold=CONTEXT_RECALL_THRESHOLD, model=DEEPEVAL_MODEL),
    }

    scores: dict[str, list[float]] = {name: [] for name in metrics}
    for test_case in test_cases:
        for name, metric in metrics.items():
            metric.measure(test_case)
            scores[name].append(metric.score)

    avg_scores = {name: sum(values) / len(values) for name, values in scores.items()}

    print("Scores (average over all goldens):")
    for name, score in sorted(avg_scores.items(), key=lambda kv: kv[1]):
        marker = " <-- below threshold" if score < _THRESHOLDS[name] else ""
        print(f"  {name:<20} {score:.3f}  (threshold {_THRESHOLDS[name]:.2f}){marker}")

    log_eval_run(avg_scores, len(test_cases), BREAK_RETRIEVAL)
    print("\nLogged to W&B (offline) -- see ./wandb/ for the run directory.")


if __name__ == "__main__":
    main()
