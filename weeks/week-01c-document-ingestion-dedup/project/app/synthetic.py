"""Synthetic corpus generator for app/demo.py's 5000-document dedup/PII/incremental-
upsert run.

Each base document is three sentences, each independently assembled from four slots
(subject/action/object/frequency) plus a unique reference-number sentence. The slot
combinatorics (~12*10*10*7 = 8400 possible sentences, 3 chosen per doc) make two
distinct base documents sharing enough content to clear the 0.85 Jaccard dedup
threshold astronomically unlikely -- verified empirically against 4950 base docs
before wiring this in (see concept.md's "Common pitfalls": a naive template-per-topic
generator with too few templates relative to corpus size creates *massive* accidental
near-duplication, which is exactly what the first version of this generator did).
Near-duplicates are then built by *appending* a short trailing clause to a specific
existing document -- appending keeps every original shingle intact, which pushes
Jaccard similarity to the source document to ~0.95, comfortably above threshold.
"""

from __future__ import annotations

import random

from app.models import RawDocument

_SUBJECTS = [
    "The support team", "The platform team", "The security team", "The finance team",
    "The mobile team", "The infrastructure team", "The data team", "The design team",
    "The legal team", "The people team", "The sales team", "The product team",
]
_ACTIONS = ["reviews", "audits", "monitors", "updates", "escalates", "documents", "schedules", "archives", "reconciles", "publishes"]
_OBJECTS = [
    "the incident backlog", "vendor contracts", "the deployment pipeline", "customer feedback",
    "access permissions", "the on-call rotation", "budget forecasts", "the security checklist",
    "the release notes", "the compliance log",
]
_FREQUENCIES = [
    "on a weekly basis", "every month", "each quarter", "every two weeks",
    "twice a year", "on a daily basis", "at the end of each sprint",
]

_PII_SENTENCES = [
    "Please contact {name} at {email} or {phone} for further details.",
    "Employee ID {emp_id} was flagged for a routine account review.",
    "For billing questions reach {name} directly at {email}.",
]
_FIRST_NAMES = ["Alex", "Priya", "Jordan", "Wei", "Fatima", "Diego", "Sam", "Nina"]
_LAST_NAMES = ["Chen", "Okafor", "Nguyen", "Silva", "Kowalski", "Haddad", "Park"]

_REVISION_CLAUSES = [
    "Reviewed quarterly.",
    "Last updated this cycle.",
    "Subject to change pending policy review.",
    "See the internal wiki for the full version history.",
    "Confirmed current as of the latest audit.",
]


def _sentence(rng: random.Random) -> str:
    return (
        f"{rng.choice(_SUBJECTS)} {rng.choice(_ACTIONS)} {rng.choice(_OBJECTS)} "
        f"{rng.choice(_FREQUENCIES)}."
    )


def _base_text(rng: random.Random) -> str:
    # 8 sentences (not 3): long enough that appending one short revision clause in
    # _perturb() changes only a small fraction of the document's shingles, keeping
    # near-duplicate Jaccard reliably above the 0.85 threshold (empirically verified
    # -- 3 sentences was too short and put ~40% of trials below threshold).
    sentences = [_sentence(rng) for _ in range(8)]
    reference = f"Reference case number {rng.randint(100000, 999999)} on file."
    return " ".join(sentences) + " " + reference


def _random_pii_sentence(rng: random.Random) -> str:
    first, last = rng.choice(_FIRST_NAMES), rng.choice(_LAST_NAMES)
    email = f"{first.lower()}.{last.lower()}@example.com"
    phone = f"{rng.randint(200, 999)}-{rng.randint(200, 999)}-{rng.randint(1000, 9999)}"
    emp_id = f"EM-{rng.randint(100000, 999999)}"
    template = rng.choice(_PII_SENTENCES)
    return template.format(name=f"{first} {last}", email=email, phone=phone, emp_id=emp_id)


def _perturb(text: str, rng: random.Random) -> str:
    return f"{text} {rng.choice(_REVISION_CLAUSES)}"


def generate_corpus(
    n_base: int = 200,
    n_near_duplicates: int = 50,
    pii_fraction: float = 0.15,
    seed: int = 42,
) -> list[RawDocument]:
    rng = random.Random(seed)
    base_docs: list[RawDocument] = []
    for i in range(n_base):
        text = _base_text(rng)
        if rng.random() < pii_fraction:
            text = f"{text} {_random_pii_sentence(rng)}"
        base_docs.append(RawDocument(id=f"doc-{i:05d}", source_path=f"synthetic://doc-{i:05d}", format="md", text=text))

    duplicates: list[RawDocument] = []
    for j in range(n_near_duplicates):
        source = rng.choice(base_docs)
        duplicates.append(
            RawDocument(
                id=f"dup-{j:05d}",
                source_path=f"synthetic://dup-{j:05d}",
                format="md",
                text=_perturb(source.text, rng),
            )
        )

    all_docs = base_docs + duplicates
    rng.shuffle(all_docs)
    return all_docs
