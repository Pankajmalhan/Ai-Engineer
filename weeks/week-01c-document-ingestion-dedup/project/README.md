# Week 1c project — document ingestion, dedup, PII redaction, incremental indexing

Implements all four weekly goals end to end:

1. **Multi-format ingestion** (`app/loaders.py`) — PDF (digital, via pdfminer;
   scanned/OCR via Tesseract+Poppler where installed), HTML, DOCX, and Markdown, all
   through Unstructured.io's `partition()`, into one unified `RawDocument` list.
2. **Near-duplicate detection** (`app/dedup.py`) — MinHash + MinHashLSH (`datasketch`)
   over word-3-shingles, dropping documents with estimated Jaccard similarity ≥ 0.85
   against an already-kept document.
3. **Incremental upsert** (`app/vectorstore.py`, `app/pipeline.py`) — a `content_hash`
   column on the pgvector `documents` table; only documents whose *raw* content hash
   changed since the last run get PII-redacted, dedup-checked, re-embedded, and
   written. A `skipped_documents` table persists dedup decisions across runs so a
   dropped duplicate doesn't get re-evaluated (or silently re-admitted) on a later run.
4. **PII redaction** (`app/pii.py`) — `RegexPIIRedactor` (email/phone/ID-shaped
   patterns, no model needed) or `PresidioPIIRedactor` (Microsoft Presidio +
   spaCy NER, catches `PERSON` on top of the regex entities) — a deliberate swap from
   raw spaCy NER per this week's tooling update, see resources.md.

`app/metrics.py` logs dedup rate and PII hit rate to W&B (`WANDB_MODE=offline` by
default — no login required). `app/pipeline.py`'s `IngestionPipeline.run()` wires all
four together. `concept.md` (one level up) explains the mechanics, the real pitfalls
hit while building this, and the tradeoffs in depth.

## What's real vs. a stand-in

Everything here is real, not mocked:

- Unstructured.io actually parses real `.md`/`.html`/`.docx`/`.pdf` fixtures
  (`tests/fixtures/`, the `.docx`/`.pdf` generated on first test run via
  `tests/generate_fixtures.py` using `python-docx`/`reportlab`).
- MinHash/LSH runs datasketch's real algorithm, not a similarity stub.
- `PGVectorStore` is a real Postgres + pgvector instance (`docker-compose.yml`),
  storing real `sentence-transformers` (`BAAI/bge-small-en-v1.5`) embeddings.
- `PresidioPIIRedactor` runs Presidio's real `AnalyzerEngine`/`AnonymizerEngine` against
  a real downloaded spaCy model (`en_core_web_sm`).
- `app/metrics.py` calls the real `wandb` SDK (offline mode by default, so runs are
  written locally under `./wandb/` with zero network calls / no API key).

The one gap: scanned-PDF OCR (`strategy="hi_res"`/`"ocr_only"` in `app/loaders.py`) is
real code but untested in this environment, which doesn't have Tesseract/Poppler
installed — `ocr_available()` gates it, and any OCR test is marked `@requires_ocr` and
skips cleanly rather than failing.

## Setup

```bash
cd project
docker compose up -d                          # starts Postgres + pgvector on localhost:5434
uv sync                                        # installs deps into .venv
uv run python -m spacy download en_core_web_sm # needed for PresidioPIIRedactor (once)
```

Without the spaCy model, `IngestionPipeline` automatically falls back to
`RegexPIIRedactor` (still catches EMAIL_ADDRESS/PHONE_NUMBER/ID_NUMBER, not PERSON).

For real scanned-PDF OCR (optional): install Tesseract and Poppler
(`brew install tesseract poppler` on macOS) so `ocr_available()` returns `True`.

## Run it

```bash
uv run python -m app.demo
```

Loads the real multi-format fixtures, then generates a 5000-document synthetic corpus
(50 intentional near-duplicates, ~15% containing PII), runs it through the full
pipeline, and reports the dedup rate, PII hit rate, and MinHash LSH's actual recall
against the known 50 near-duplicates. It then edits 25 documents and re-runs the
pipeline to measure the incremental-upsert speedup from the content-hash skip logic
(measured ~110x on this corpus: ~150s full ingest vs. ~1.4s for the 25-document delta).

## Tests

```bash
uv run pytest
```

Tests that need Postgres/pgvector are marked `@requires_postgres` and skip cleanly if
`docker compose up -d` hasn't been run; tests needing the Presidio spaCy model are
marked `@requires_presidio` and skip cleanly if it hasn't been downloaded; OCR tests
are marked `@requires_ocr`. Covers: loading every supported format from real files,
MinHash near-dup detection (including a 50-duplicate batch), both PII redactors,
incremental upsert (first-write / no-op-rerun / partial-change), the full pipeline
(dedup + redact + upsert together, including a dropped duplicate staying dropped
across a later rerun), and offline W&B metric logging.
