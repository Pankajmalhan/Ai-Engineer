"""Shared plain-data types for the ingestion pipeline: load -> redact -> dedup -> upsert."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field


def content_hash(text: str) -> str:
    """Stable hash of a document's text, used by PGVectorStore to decide whether a row
    needs re-embedding on incremental upsert (see vectorstore.py)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class RawDocument:
    """One file loaded from disk, before any processing."""

    id: str
    source_path: str
    format: str  # "pdf" | "html" | "docx" | "md"
    text: str


@dataclass
class PIIMatch:
    entity_type: str  # e.g. "EMAIL_ADDRESS", "PHONE_NUMBER", "ID_NUMBER", "PERSON"
    text: str
    start: int
    end: int


@dataclass
class ProcessedDocument:
    """A RawDocument after PII redaction, ready for dedup + indexing."""

    id: str
    source_path: str
    format: str
    text: str  # redacted text
    pii_matches: list[PIIMatch] = field(default_factory=list)
    hash: str = ""

    def __post_init__(self):
        if not self.hash:
            self.hash = content_hash(self.text)


@dataclass
class DuplicatePair:
    kept_id: str
    dropped_id: str
    jaccard: float


@dataclass
class UpsertStats:
    upserted: int
    skipped: int
    elapsed_seconds: float = 0.0
