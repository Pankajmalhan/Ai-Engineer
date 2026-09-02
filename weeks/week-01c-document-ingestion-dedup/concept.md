# Week 1c — Document Ingestion, Deduplication, and Incremental Indexing

## Overview

Every RAG system so far in this roadmap has assumed a clean, static corpus already
sitting in the vector store. Real corpora aren't clean or static: they arrive as a mix
of PDFs (some digital, some scanned), HTML exports, Word docs, and Markdown; the same
document gets ingested twice with a formatting change; a support ticket has a
customer's email and phone number sitting in plain text; and the corpus grows every
day, so re-embedding all of it on every ingestion run is either too slow or too
expensive to keep doing. This week is about the unglamorous but load-bearing layer
underneath retrieval quality: getting messy real-world documents into a *correct,
deduplicated, PII-safe, incrementally-updatable* index in the first place. Get this
layer wrong and no amount of hybrid search, reranking, or corrective RAG on top of it
will fix an index that's 30% duplicate content or leaking customer PII into an LLM
prompt.

## Core concept, in depth

### 1. Unified multi-format ingestion (Unstructured.io)

`app/loaders.py` calls Unstructured's `partition()` once per file; it auto-detects the
format from the extension and dispatches to a format-specific partitioner (pdfminer
for digital PDF text, python-docx for `.docx`, lxml/BeautifulSoup for `.html`, a
markdown parser for `.md`), returning a flat list of typed `Element`s (`Title`,
`NarrativeText`, `Table`, ...). The loader flattens that back into one plain-text
string per document — deliberately not richer than that for this week, since dedup and
PII redaction both operate on plain text; a system that also wanted to preserve
document structure (e.g., to chunk by section) would keep the element list instead.

**Digital vs. scanned PDFs are a different problem, not a flag.** A digital PDF has a
real text layer — pdfminer just reads it out, no OCR needed (`pdf_strategy="fast"` in
this project, real and default). A scanned PDF is a picture of a page with no text
layer at all; `partition_pdf` handles that via `strategy="hi_res"`/`"ocr_only"`, which
renders each page to an image (needs Poppler's `pdftoppm`) and runs Tesseract OCR on
it. Both code paths exist in `app/loaders.py` (`ocr_available()` gates on `tesseract`
+ `pdftoppm` being on `PATH`), but this project's dev environment doesn't have Poppler/
Tesseract installed, so the OCR path is real but untested here — `tests/test_loaders.py`
only exercises the digital-PDF path, and any OCR-only test would be marked
`@requires_ocr` and skip cleanly rather than fail. This is a genuine, common deployment
gap: OCR needs system binaries a plain `pip install` doesn't give you, so "PDF support"
in a demo often silently means "digital PDF support" until someone feeds it a scan.

### 2. Near-duplicate detection: MinHash LSH

**The problem MinHash solves.** Exact-duplicate detection is trivial — hash the whole
document, compare hashes. Near-duplicate detection (two documents that differ by a
timestamp, a reformatting pass, or a single edited paragraph) needs a similarity
measure, and the standard one for text is **Jaccard similarity over shingles**: break
each document into overlapping word n-grams ("shingles" — this project uses 3-grams,
`MINHASH_SHINGLE_SIZE`), treat each document as the *set* of its shingles, and compute
`|A ∩ B| / |A ∪ B|`. Two documents that share almost all their shingles score close to
1.0; two unrelated documents score close to 0.

Computing exact Jaccard for every pair in a large corpus is O(n²) set intersections —
infeasible past a few thousand documents. **MinHash** approximates Jaccard cheaply: for
each document's shingle set, apply `num_perm` independent hash functions and keep only
the *minimum* hash value each one produces (`app/dedup.py`'s `_minhash`). The
mathematical fact that makes this work: for two sets A and B, the probability that a
random permutation's minimum hash agrees between A and B equals `Jaccard(A, B)`
*exactly*. So averaging agreement across `num_perm` independent permutations gives an
unbiased estimator of Jaccard, and it comes out to a fixed-size signature (128 or 256
numbers) regardless of how many shingles the document actually has. **LSH
(locality-sensitive hashing)** then avoids comparing every signature pair directly: it
splits each signature into `b` bands of `r` rows and buckets documents by band
contents, so two documents only become "candidates" if at least one band matches
exactly — datasketch's `MinHashLSH` picks `b`/`r` automatically from your `threshold`
to balance false positives against false negatives. `find_near_duplicates()` still
double-checks every LSH candidate with an exact-on-signature `mh.jaccard()` call before
actually dropping anything (LSH's candidate set is recall-biased, not precision-biased
— see Common Pitfalls).

**A concrete worked example**, built while writing this project's `app/synthetic.py`
demo corpus generator: the base text

> "Our refund policy allows a full refund within thirty days of purchase for annual
> plans... [~50 more words]"

as 3-word shingles is a set of ~45 strings like `{"our refund policy", "refund policy
allows", "policy allows a", ...}`. Editing one word in place (`"thirty days"` →
`"thirty dayz"`) only invalidates the ~3 shingles that word appears in — but on a
~45-word document that's still enough to occasionally land Jaccard *right at* the 0.85
threshold rather than comfortably above it (measured: exactly 0.85). *Appending* a
short clause instead (`+ " Reviewed quarterly."`) keeps every original shingle intact
and only adds a handful of new boundary shingles, landing around 0.88-0.97 depending on
document length — a much safer margin. This distinction — in-place edits dilute more of
the *existing* shingle set per word changed than appends do — is exactly the kind of
thing that's invisible until you compute real numbers, which is why this project's
tests and demo do so explicitly rather than assuming "near-duplicate" text is
obviously near-duplicate to the algorithm.

### 3. Incremental upsert via content hash

`PGVectorStore` (`app/vectorstore.py`) adds a `content_hash` column (SHA-256 of the raw
source text) to the `documents` table. `IngestionPipeline.run()` (`app/pipeline.py`)
hashes every incoming raw document *before* doing anything else, looks up the stored
hash for each id, and only sends documents whose hash actually changed (or that are new)
through PII redaction, dedup, and embedding. A document whose hash matches what's
already stored is skipped **entirely** — not just the embedding call, the redaction
pass too, since redaction is a deterministic function of the raw input and an unchanged
input redacts to the same output every time.

That last point mattered enough to be worth a real mistake and fix: the first version
of this pipeline hashed the *redacted* text and only skipped the final embed+write step
for unchanged documents, but still ran every document through Presidio's NER pass on
every run regardless of whether anything had changed. On the 5000-document demo
corpus, that meant re-scanning ~5000 documents through spaCy's NER pipeline even when
only 25 had actually changed — the incremental run measured **1.3-1.6x** faster than a
full re-ingest, i.e. barely incremental at all, because the expensive step (NER) still
ran on everything. Moving the hash to the raw input and skipping redaction itself for
unchanged documents brought the same 25-changed-of-5000 scenario to **~110x** faster
(1.4s vs. ~150s) — the actual point of a content-hash column is to skip the *expensive
upstream work*, not just the final write.

**Dropped duplicates need their decision persisted too.** A document MinHash LSH drops
as a near-duplicate never gets a row in `documents` — so a naive "is there a stored hash
for this id" check would see nothing, call it "changed" on *every* subsequent run, and
re-run it through redaction and dedup indefinitely. Worse: because dedup only compares
documents *within the current run's batch*, a later incremental run that includes the
previously-dropped document but *not* the original it was a near-duplicate of would
have no way to recognize it as a duplicate anymore, and would incorrectly upsert it as
a new "unique" document — silently undoing the original dedup decision. This project's
`skipped_documents` table (`app/vectorstore.py`) exists specifically to close that gap:
every dropped duplicate's id and hash gets recorded there, so `existing_hashes()` (used
by both the pipeline's own change-detection and `incremental_upsert`'s) treats it as
"already decided" and skips it, the same as an indexed document with an unchanged hash.
This was caught empirically, not designed in from the start: an early version of the
5000-doc, 25-edited-doc incremental demo run showed 71 documents upserted instead of
the expected 25, and the extra 46 were exactly the near-duplicates dropped in the first
run resurfacing as false-uniques in the second.

### 4. PII redaction: regex vs. Presidio

Two implementations behind the same interface (`app/pii.py`), the same
heuristic/real split every prior week's grader/refiner/rewriter used:

- **`RegexPIIRedactor`** — pattern-matches email addresses, phone numbers, and
  ID-number-shaped strings (`EM-482913`, SSN-shaped `123-45-6789`). Free, instant, zero
  model download. Blind to anything without a fixed shape — a name, a street address —
  because those aren't *patterns*, they're context-dependent judgments.
- **`PresidioPIIRedactor`** — Microsoft Presidio's `AnalyzerEngine`, backed by spaCy NER
  (`en_core_web_sm`), plus this project's custom `PatternRecognizer` for the same
  `ID_NUMBER` shapes the regex redactor catches. Presidio adds entities regex
  fundamentally can't: `PERSON`, and (not used here, but available)
  `LOCATION`/`ORGANIZATION`/etc. This is a deliberate substitution for a raw
  spaCy-NER-only pass — see resources.md's tooling update — because Presidio wraps
  spaCy with purpose-built PII recognizers, confidence scoring, and an `AnonymizerEngine`
  that does the actual text replacement, instead of hand-rolling entity-to-redaction
  logic on top of raw spaCy NER output.

`IngestionPipeline` picks `PresidioPIIRedactor` if the spaCy model is downloaded,
falling back to `RegexPIIRedactor` otherwise (`presidio_available()`) — the same
graceful-degradation pattern the vectorstore's `is_available()` and prior weeks'
`ANTHROPIC_API_KEY`-gated redactors use.

## Why it matters in production

- **Format diversity is the default, not the edge case.** A real internal knowledge
  base is Confluence exports (HTML), old policy PDFs (some scanned from paper),
  contracts (DOCX), and READMEs (Markdown) — a pipeline that only handles one format
  silently excludes whole categories of the corpus a user expects to be searchable.
- **Duplicate content measurably hurts retrieval and generation**, not just storage
  cost. The Lee et al. 2022 paper this week's resources cite (skim Section 2) found
  that near-duplicate training data causes disproportionate memorization and quality
  loss in language models; the retrieval-time analogue is a top-k that returns 3
  near-identical chunks of the *same* underlying content instead of 3 chunks covering
  different information, which degrades answer diversity and coverage even though every
  individual chunk is "relevant."
- **Incremental indexing is what makes daily/hourly re-ingestion economically
  possible.** A 5000-document corpus that takes ~2.5 minutes to fully re-embed and
  index costs that same 2.5 minutes on *every single ingestion run* without a
  content-hash diff — at real-world corpus sizes (hundreds of thousands to millions of
  documents), re-embedding everything on every run isn't slow, it's simply not done,
  which means the index silently drifts stale unless someone builds exactly this
  mechanism.
- **PII leaking into a vector store is a compliance incident, not a bug ticket.**
  Once an email address or ID number is embedded and indexed, it's retrievable by
  *any* query that happens to be semantically close to it, and it may get pasted
  directly into an LLM's context window and, depending on logging, into observability
  systems downstream. Redaction has to happen *before* the embedding call, not as a
  post-hoc filter on retrieved results.

## Tradeoffs & comparisons

| | RegexPIIRedactor | PresidioPIIRedactor |
|---|---|---|
| Setup cost | None | `spacy download en_core_web_sm` once |
| Speed | Instant, no model inference | NER inference per document (real but small cost) |
| Catches EMAIL/PHONE/ID_NUMBER | Yes | Yes (plus custom pattern recognizers) |
| Catches PERSON/LOCATION/etc. | No — no fixed shape to match | Yes — real NER |
| Failure mode | False negatives on anything without a fixed pattern | False negatives/positives from NER miscalibration on unusual name formats |

| | Exact-hash dedup | MinHash LSH near-dedup |
|---|---|---|
| Catches identical documents | Yes | Yes |
| Catches reformatted/lightly-edited duplicates | No | Yes (approximately) |
| Cost at scale | O(n), trivial | O(n) amortized via banding, but approximate |
| Recall | 100% (it's exact) | Not 100% — see Common Pitfalls |

**Full re-embed vs. content-hash incremental upsert**: full re-embed is simpler (no
hash bookkeeping, no `skipped_documents` table to keep consistent) and guarantees the
index always reflects a clean recomputation. Incremental upsert is dramatically
cheaper at scale (measured ~110x on this project's 5000-doc/25-changed scenario) but
only as correct as its change-detection and skip-persistence logic — get either wrong
(as this project's first two iterations did) and you either lose the speed advantage
or silently let deduplication decisions un-decide themselves over time.

## Common pitfalls

- **A synthetic/test corpus with too little textual diversity relative to its size
  produces massive *accidental* near-duplication, drowning out the near-duplicates you
  meant to test.** The first version of this project's demo corpus generator reused 8
  fixed paragraph templates across 4950 "unique" documents (~600 docs/template) — MinHash
  LSH correctly found that ~32% of the corpus was near-duplicate, because with that few
  templates it *was*. The fix wasn't a code bug fix, it was generating genuinely
  diverse text (combinatorial sentence assembly from independent subject/action/object/
  frequency slots, ~8400 possible sentences). This generalizes: if you're building or
  evaluating a dedup pipeline against synthetic data, verify your "unique" documents are
  actually unique to the algorithm, not just to a human skimming them.
- **In-place word edits are a weaker near-duplicate signal than they look.** A single
  word swapped in a ~40-word document can land Jaccard *exactly* at a threshold like
  0.85 rather than comfortably above it — fine most of the time, fragile as a test
  fixture or a "guaranteed to be caught" scenario. Prefer edits (or realistic near-dup
  scenarios) with a clear similarity margin above whatever threshold you're using.
- **MinHash LSH's recall is not 100%, even for pairs genuinely above your threshold.**
  This project measured it directly: 50 near-duplicate documents with *true* Jaccard
  between 0.88 and 0.98 (verified by exact computation, not estimated) — at
  `num_perm=128`, LSH's candidate-bucketing missed 10 of them (80% recall); at
  `num_perm=256`, it missed 4 (92% recall); `num_perm=512` didn't improve further. This
  isn't a bug — it's LSH's banding technique trading recall for the ability to avoid
  comparing every pair directly, and the S-curve it produces means recall is genuinely
  imperfect near the threshold no matter how many permutations you use, though it
  improves the further above threshold a true pair's similarity sits. **Practical
  implication:** don't assume "our dedup rate is right" without spot-checking recall
  against known duplicates; if a use case truly needs near-100% recall, either use a
  much higher `num_perm`, a lower effective threshold with a stricter exact-check pass,
  or accept it as a probabilistic pre-filter feeding into a smaller exact-comparison
  step rather than the final decision-maker.
- **Hashing the wrong thing collapses the entire point of incremental indexing.**
  Hashing post-redaction text instead of raw input text means every document still
  pays the redaction cost on every run (measured: 1.3-1.6x vs. ~110x speedup — see Core
  Concept #3). More generally: the hash used for change detection should be computed as
  early in the pipeline as possible, before any expensive deterministic transformation,
  so that transformation gets skipped too.
- **A dedup decision that isn't persisted isn't a decision, it's a coin flip on the
  next run.** Dropping a near-duplicate without recording that it was dropped (and why)
  means a later incremental run can silently re-admit it — see Core Concept #3's
  `skipped_documents` fix. Any "we filtered this out" step in a pipeline that runs more
  than once needs its own durable record, not just an in-memory decision for the
  current run.
- **OCR "support" that was never actually run against a real scanned document isn't
  verified support.** This project's PDF loader has a real `hi_res`/`ocr_only` code
  path, but the dev environment lacks Tesseract/Poppler, so that path has never
  actually executed here — it's marked `@requires_ocr` and skips rather than silently
  passing. Don't conflate "the code exists" with "the code works" for any dependency
  that isn't actually installed in CI/dev.

## Check yourself

1. Two documents have true Jaccard similarity of 0.90 on their word-3-shingles, well
   above a 0.85 dedup threshold. Explain concretely (in terms of MinHash + LSH
   banding) why they might still not be flagged as duplicates, and what you'd change
   to make detection more reliable.
2. Why does hashing the *raw* input (before PII redaction) instead of the *redacted*
   output matter for incremental-upsert performance, given that redaction is a pure,
   deterministic function of the raw input either way?
3. A document gets dropped as a near-duplicate on ingestion run 1. On run 2, the exact
   same raw bytes are ingested again, but the document it was originally a duplicate of
   isn't part of run 2's batch at all. Walk through what happens with and without a
   `skipped_documents`-style persisted skip record.
4. Your PII hit rate (fraction of ingested documents containing detected PII) jumps
   from 5% to 40% between two ingestion runs of the same general document source, with
   no known change in the underlying data. List two possible causes on the *pipeline*
   side (not the data side) and how you'd distinguish them.
5. `RegexPIIRedactor` and `PresidioPIIRedactor` are given the same document containing
   a person's name next to their employee ID. Which entities does each one catch, which
   does each one miss, and why does the difference matter for a document that's about
   to be embedded and made retrievable?
