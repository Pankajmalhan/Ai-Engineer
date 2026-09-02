"""Wires the four weekly pieces into one call: hash raw input -> skip anything
unchanged since the last run -> redact PII -> drop near-duplicates -> incremental
upsert -> (optionally) log data-quality metrics.

The change-detection hash is computed on the *raw* (pre-redaction) text, not the
redacted text: redaction is a deterministic function of the raw input, so if the raw
hash matches what's already stored, the previously-redacted content is already
correct and doesn't need re-processing. This is what makes incremental re-ingestion
actually cheap -- an unchanged document skips PII redaction (a real NER pass) and
dedup consideration entirely, not just the final embed+write, which is where most of
the wall-clock time in a large batch goes.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from app.dedup import dedup_rate, find_near_duplicates
from app.metrics import log_ingestion_run
from app.models import DuplicatePair, ProcessedDocument, RawDocument, UpsertStats, content_hash
from app.pii import PresidioPIIRedactor, RegexPIIRedactor, presidio_available
from app.vectorstore import PGVectorStore


@dataclass
class IngestionReport:
    total_documents: int
    unchanged_documents: int
    duplicates: list[DuplicatePair]
    pii_hits: int
    documents_with_pii: int
    upsert_stats: UpsertStats


class IngestionPipeline:
    def __init__(self, store: PGVectorStore, redactor=None):
        self.store = store
        # PresidioPIIRedactor needs `spacy download en_core_web_sm` once; falls back
        # to the regex-only redactor (still catches EMAIL/PHONE/ID_NUMBER) if that
        # model hasn't been downloaded, mirroring prior weeks' Heuristic/real split.
        self.redactor = redactor or (PresidioPIIRedactor() if presidio_available() else RegexPIIRedactor())

    def _redact(self, raw_docs: list[RawDocument], raw_hashes: dict[str, str]) -> list[ProcessedDocument]:
        processed = []
        for raw in raw_docs:
            redacted_text, matches = self.redactor.redact(raw.text)
            doc = ProcessedDocument(
                id=raw.id,
                source_path=raw.source_path,
                format=raw.format,
                text=redacted_text,
                pii_matches=matches,
            )
            # Keyed on the *raw* hash, not hash(redacted_text): the vectorstore's
            # content_hash column is the change-detection key for the source
            # document, so a re-run's hash lookup (here and inside
            # PGVectorStore.incremental_upsert) compares against the same thing.
            doc.hash = raw_hashes[raw.id]
            processed.append(doc)
        return processed

    def run(self, raw_docs: list[RawDocument], log_metrics: bool = False) -> IngestionReport:
        start = time.perf_counter()
        raw_hashes = {d.id: content_hash(d.text) for d in raw_docs}
        stored_hashes = self.store.existing_hashes(list(raw_hashes))
        changed_raw = [d for d in raw_docs if stored_hashes.get(d.id) != raw_hashes[d.id]]
        unchanged_count = len(raw_docs) - len(changed_raw)

        processed = self._redact(changed_raw, raw_hashes)
        pii_hits = sum(len(d.pii_matches) for d in processed)
        documents_with_pii = sum(1 for d in processed if d.pii_matches)

        unique, duplicates = find_near_duplicates(processed)

        if duplicates:
            processed_by_id = {d.id: d for d in processed}
            self.store.mark_skipped([(p.dropped_id, processed_by_id[p.dropped_id].hash) for p in duplicates])

        upsert_stats = self.store.incremental_upsert(unique)
        upsert_stats = UpsertStats(
            upserted=upsert_stats.upserted,
            skipped=unchanged_count + upsert_stats.skipped,
            elapsed_seconds=time.perf_counter() - start,
        )

        report = IngestionReport(
            total_documents=len(raw_docs),
            unchanged_documents=unchanged_count,
            duplicates=duplicates,
            pii_hits=pii_hits,
            documents_with_pii=documents_with_pii,
            upsert_stats=upsert_stats,
        )

        if log_metrics:
            log_ingestion_run(
                total_documents=report.total_documents,
                duplicates_dropped=len(duplicates),
                dedup_rate=dedup_rate(len(processed), len(duplicates)),
                pii_hits=pii_hits,
                documents_with_pii=documents_with_pii,
                pii_hit_rate=(documents_with_pii / len(processed)) if processed else 0.0,
                upserted=upsert_stats.upserted,
                skipped=upsert_stats.skipped,
                elapsed_seconds=upsert_stats.elapsed_seconds,
            )

        return report
