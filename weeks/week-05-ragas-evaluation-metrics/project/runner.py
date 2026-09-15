"""Standalone debug script for app/evaluate.py. Runs the RAG pipeline + full RAGAS
metric suite over the dataset and prints per-metric scores plus the weakest metric.

Needs OPENAI_API_KEY (real cost: pipeline generation + RAGAS's LLM-judged metrics +,
if INCLUDE_SYNTHETIC is on, 40 synthetic-QA generation calls) -- prints a clear
message and exits if it isn't set, same pattern as week 1c's Postgres check.

Defaults to the 10 hand-labeled samples only, to keep a debug loop cheap and fast.
Set INCLUDE_SYNTHETIC=1 to run the full 50-sample set the roadmap task specifies.

Run with: uv run python runner.py
Run with: INCLUDE_SYNTHETIC=1 uv run python runner.py
"""

import os

from app.dataset import HAND_LABELED, generate_synthetic_samples
from app.evaluate import run_evaluation
from app.llm import openai_available
from app.wandb_logging import log_evaluation_run


def main() -> None:
    if not openai_available():
        print(
            "OPENAI_API_KEY is not set -- this project needs a real OpenAI key for "
            "pipeline generation and RAGAS's LLM-judged metrics. Set it and re-run:\n"
            "  export OPENAI_API_KEY=sk-...\n"
            "  uv run python runner.py"
        )
        return

    samples = list(HAND_LABELED)
    if os.environ.get("INCLUDE_SYNTHETIC") == "1":
        print("Generating 40 synthetic samples with OPENAI_MODEL...")
        samples += generate_synthetic_samples()
    print(f"Evaluating {len(samples)} sample(s) ({'hand-labeled only' if len(samples) == 10 else 'hand-labeled + synthetic'})...\n")

    summary = run_evaluation(samples)

    print(f"RAGAS API resolved: {summary.api_version}")
    print(f"Sample count       : {summary.sample_count}\n")
    print("Scores:")
    for metric, score in sorted(summary.scores.items(), key=lambda kv: kv[1]):
        marker = " <-- weakest" if metric == summary.weakest_metric else ""
        print(f"  {metric:<25} {score:.3f}{marker}")

    log_evaluation_run(summary.scores, summary.sample_count, summary.weakest_metric)
    print("\nLogged to W&B (offline) -- see ./wandb/ for the run directory.")


if __name__ == "__main__":
    main()
