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


# Paraphrases of the 8 goldens above (same reference answer and source document, different
# wording). 8 questions is too few for a stable faithfulness mean -- one flipped answer moves
# it by 0.12 -- so the extended set triples the sample and also varies the phrasing, which
# keeps the load test from replaying 8 identical prompts. Retrieval can legitimately miss a
# paraphrase that shares no keywords with the passage (BM25 is lexical); the harness reports
# that as retrieval_hit, separate from generation quality.
_PARAPHRASES: dict[str, list[str]] = {
    "refunds": [
        "What's the refund window for an annual subscription?",
        "If I cancel my yearly plan, within how many days can I get my money back?",
    ],
    "rate-limits": [
        "How many requests per minute can a Pro account make?",
        "What is the Pro plan's API rate limit per minute?",
    ],
    "auth": [
        "After I rotate my API key, how long is the previous key still valid?",
        "When does my old API key stop working once I rotate it?",
    ],
    "data-retention": [
        "How long do you retain request logs?",
        "After how many days are my request logs permanently deleted?",
    ],
    "uptime-sla": [
        "What monthly uptime does the Pro tier SLA guarantee?",
        "What uptime percentage is guaranteed for Pro?",
    ],
    "billing-cycle": [
        "How much do I save by paying annually instead of monthly?",
        "What is the discount for annual billing versus monthly billing?",
    ],
    "support-sla": [
        "What is the first response time for Pro tier support tickets?",
        "How fast does support first respond to a Pro ticket?",
    ],
    "webhooks": [
        "How many retries does a failed webhook delivery get?",
        "How many times is a failed webhook delivery retried, and over what period?",
    ],
}

EXTENDED_GOLDENS: list[EvalSample] = list(GOLDENS) + [
    EvalSample(question=q, reference=g.reference, source_doc_id=g.source_doc_id)
    for g in GOLDENS
    for q in _PARAPHRASES[g.source_doc_id]
]
