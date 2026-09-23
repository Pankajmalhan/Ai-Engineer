"""The RAGAS-shaped golden set this week pushes into Braintrust: one question/reference
pair per corpus passage, written directly against app/corpus.py so ground truth is
exact, not paraphrased by a model -- same reasoning as Week 6's hand-written GOLDENS.
Only question/reference/source_doc_id are stored; retrieved_contexts and the pipeline's
answer are produced at eval/push time by actually running RAGPipeline, so this dataset
stays a fixed fixture independent of pipeline changes.
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
