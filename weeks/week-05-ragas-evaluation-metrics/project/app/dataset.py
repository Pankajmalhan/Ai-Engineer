"""Builds the 50-sample evaluation dataset: 10 hand-labeled question/reference pairs
(HAND_LABELED, written directly against app/corpus.py so each fact is traceable to one
passage) plus 40 synthetically generated via OPENAI_MODEL (generate_synthetic_samples).

Only the question and reference answer are stored here -- retrieved_contexts and the
pipeline's response are produced at evaluation time by actually running RAGPipeline
(app/evaluate.py), not baked into the dataset, so the dataset stays a fixed regression
fixture independent of pipeline changes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from app.config import SYNTHETIC_COUNT
from app.corpus import CORPUS
from app.llm import openai_available


@dataclass
class EvalSample:
    question: str
    reference: str
    source_doc_id: str
    label: str  # "hand" | "synthetic"


# 10 hand-labeled samples -- one per corpus passage, written directly from the source
# text so the ground truth is exact, not paraphrased by a model.
HAND_LABELED: list[EvalSample] = [
    EvalSample(
        question="How many days do I have to request a refund on an annual plan?",
        reference="30 days from the date of purchase, for a full refund.",
        source_doc_id="refunds",
        label="hand",
    ),
    EvalSample(
        question="What's the API rate limit on the Pro tier?",
        reference="600 requests per minute.",
        source_doc_id="rate-limits",
        label="hand",
    ),
    EvalSample(
        question="How long does my old API key keep working after I rotate it?",
        reference="24 hours after rotation.",
        source_doc_id="auth",
        label="hand",
    ),
    EvalSample(
        question="How long are request logs kept before deletion?",
        reference="90 days, after which they are permanently deleted.",
        source_doc_id="data-retention",
        label="hand",
    ),
    EvalSample(
        question="What uptime percentage does the Pro tier SLA guarantee?",
        reference="99.9% uptime, measured monthly.",
        source_doc_id="uptime-sla",
        label="hand",
    ),
    EvalSample(
        question="What discount do I get for paying annually instead of monthly?",
        reference="20% off versus paying monthly.",
        source_doc_id="billing-cycle",
        label="hand",
    ),
    EvalSample(
        question="How fast do Pro tier support tickets get a first response?",
        reference="Within 4 business hours.",
        source_doc_id="support-sla",
        label="hand",
    ),
    EvalSample(
        question="How do I export my account data, and how long does it take?",
        reference=(
            "From the dashboard's Settings > Export page; the export is emailed as a "
            "download link within about 15 minutes."
        ),
        source_doc_id="data-export",
        label="hand",
    ),
    EvalSample(
        question="How many times will a failed webhook delivery be retried?",
        reference="Up to 5 times, with exponential backoff over 24 hours.",
        source_doc_id="webhooks",
        label="hand",
    ),
    EvalSample(
        question="How long is a password reset link valid for?",
        reference="1 hour, and it can only be used once.",
        source_doc_id="password-reset",
        label="hand",
    ),
]

_SYNTHETIC_SYSTEM_PROMPT = (
    "Given a documentation passage, write {n} distinct question/answer pairs a real "
    "user might ask that are answerable directly from the passage. Answers must be "
    "short (one sentence) and stated only using facts in the passage -- do not add "
    "outside information. Return a strict JSON object of the form "
    '{{"questions": [{{"question": "...", "answer": "..."}}, ...]}}.'
)


def generate_synthetic_samples(n: int = SYNTHETIC_COUNT) -> list[EvalSample]:
    """Generates n synthetic samples spread evenly across the corpus using
    OPENAI_MODEL. Requires OPENAI_API_KEY -- raises RuntimeError otherwise so callers
    fail loudly rather than silently returning an empty/partial dataset."""
    if not openai_available():
        raise RuntimeError(
            "OPENAI_API_KEY is not set -- synthetic dataset generation needs a real "
            "OpenAI call. Set the key and re-run, or use HAND_LABELED alone for a "
            "smaller, cost-free dataset."
        )

    from app.llm import _client
    from app.config import OPENAI_MODEL

    per_doc = max(1, n // len(CORPUS))
    samples: list[EvalSample] = []
    client = _client()
    for doc in CORPUS:
        if len(samples) >= n:
            break
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": _SYNTHETIC_SYSTEM_PROMPT.format(n=per_doc)},
                {"role": "user", "content": doc.text},
            ],
            temperature=0.7,
            response_format={"type": "json_object"},
        )
        payload = json.loads(response.choices[0].message.content)
        pairs = payload if isinstance(payload, list) else payload.get("questions", payload.get("data", []))
        for pair in pairs:
            if len(samples) >= n:
                break
            samples.append(
                EvalSample(
                    question=pair["question"],
                    reference=pair["answer"],
                    source_doc_id=doc.id,
                    label="synthetic",
                )
            )
    return samples


def build_dataset(include_synthetic: bool = True) -> list[EvalSample]:
    samples = list(HAND_LABELED)
    if include_synthetic:
        samples += generate_synthetic_samples()
    return samples
