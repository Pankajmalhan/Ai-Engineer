"""Pushes app.dataset.GOLDENS into Braintrust as a versioned Dataset (Braintrust's own
term for a reusable collection of cases -- distinct from an *experiment*, which is one
scored run over a dataset; see evals/rag_quality.eval.py for the experiment side).

Run with: uv run python -m app.braintrust_push
Requires BRAINTRUST_API_KEY -- braintrust_available() gates this so importing this
module, or running it without a key, never makes a network call.
"""

from __future__ import annotations

import os

from app.dataset import GOLDENS

PROJECT_NAME = "northwind-rag-week8"
DATASET_NAME = "ragas-golden-set"


def braintrust_available() -> bool:
    return bool(os.environ.get("BRAINTRUST_API_KEY"))


def push_dataset() -> int:
    """Inserts one row per GOLDENS entry into the Braintrust dataset, keyed by
    source_doc_id so re-running this is an upsert, not a duplicate append. Returns the
    number of rows inserted.
    """
    if not braintrust_available():
        raise RuntimeError("BRAINTRUST_API_KEY is not set -- sign up at braintrust.dev and export it first")

    from braintrust import init_dataset

    dataset = init_dataset(project=PROJECT_NAME, name=DATASET_NAME)
    for sample in GOLDENS:
        dataset.insert(
            input=sample.question,
            expected=sample.reference,
            metadata={"source_doc_id": sample.source_doc_id},
        )
    dataset.flush()
    return len(GOLDENS)


if __name__ == "__main__":
    n = push_dataset()
    print(f"Pushed {n} rows to Braintrust project '{PROJECT_NAME}', dataset '{DATASET_NAME}'.")
