"""The fixed golden set this week's CI gate runs against.

Unlike Week 5's 50-sample dataset (10 hand-labeled + 40 LLM-synthesized), this stays
small and entirely hand-written -- no synthetic expansion. A gate that runs on every
`git push` needs to be cheap and deterministic: regenerating goldens via an LLM call on
every push adds cost to every commit and makes the gate itself non-deterministic (see
concept.md's "Why the CI dataset is small and fixed" section). Put breadth in a
separate, less-frequent benchmark job instead of growing this file.

Each GOLDENS entry maps directly onto what DeepEval calls a `Golden` (question +
expected_output, without the retrieval/generation fields -- those get filled in by
actually running the pipeline at test time, in app/deepeval_cases.py).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EvalSample:
    question: str
    reference: str
    source_doc_id: str


GOLDENS: list[EvalSample] = [
    EvalSample(
        question="How many days do I have to request a refund on an annual plan?",
        reference="30 days from the date of purchase, for a full refund.",
        source_doc_id="refunds",
    ),
    EvalSample(
        question="What's the API rate limit on the Pro tier?",
        reference="600 requests per minute.",
        source_doc_id="rate-limits",
    ),
    EvalSample(
        question="How long does my old API key keep working after I rotate it?",
        reference="24 hours after rotation.",
        source_doc_id="auth",
    ),
    EvalSample(
        question="How long are request logs kept before deletion?",
        reference="90 days, after which they are permanently deleted.",
        source_doc_id="data-retention",
    ),
    EvalSample(
        question="What uptime percentage does the Pro tier SLA guarantee?",
        reference="99.9% uptime, measured monthly.",
        source_doc_id="uptime-sla",
    ),
    EvalSample(
        question="What discount do I get for paying annually instead of monthly?",
        reference="20% off versus paying monthly.",
        source_doc_id="billing-cycle",
    ),
    EvalSample(
        question="How fast do Pro tier support tickets get a first response?",
        reference="Within 4 business hours.",
        source_doc_id="support-sla",
    ),
    EvalSample(
        question="How many times will a failed webhook delivery be retried?",
        reference="Up to 5 times, with exponential backoff over 24 hours.",
        source_doc_id="webhooks",
    ),
]
