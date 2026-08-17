# Hybrid Search (pgvector + pg_search BM25 + RRF)

Week 1 project: a Postgres-native hybrid retriever. Dense candidates come from
`pgvector` (HNSW, cosine distance), sparse/BM25 candidates come from ParadeDB's
`pg_search` extension, and the two ranked lists are merged with Reciprocal Rank
Fusion. See [`../concept.md`](../concept.md) for the theory this implements.

Both extensions ship together in the `paradedb/paradedb` Docker image, so there's
no separate install step for either.

## Install

```bash
uv sync
```

## Run Postgres (pgvector + pg_search)

```bash
docker compose up -d
```

This starts ParadeDB on `localhost:5433` (not 5432, to avoid clashing with a local
Postgres). Copy `.env.example` to `.env` if you want to override the connection
string, embedding model, or RRF `k`.

## Ingest the benchmark corpus

```bash
uv run python -m app.ingest
```

Creates the `documents` table (dense `vector(384)` column + HNSW index, BM25 index
via `pg_search`), embeds all 70 corpus documents with a local model
(`BAAI/bge-small-en-v1.5`, via `fastembed` — no API key needed, downloads once on
first run), and loads them.

## Run the benchmark

```bash
uv run python -m app.benchmark
```

Runs the 20 queries in `app/corpus.py` and reports recall@10 for dense-only,
sparse-only, and hybrid (RRF). **Measured result on this corpus**: dense-only and
hybrid both hit 100% recall@10, while sparse-only drops to 90% (misses 2 of 10
semantic/paraphrase queries outright). Dense-only already wins here because
`bge-small`'s subword tokenizer turns out to preserve rare alphanumeric tokens
(error codes, SKUs, CVE-style IDs) well enough that even a literal-substring query
still embeds close to its one matching document — a genuinely useful thing to know,
and not something you'd guess from theory alone. See the note printed at the end of
the benchmark run, and `tests/test_retrieval.py`, for where hybrid's value actually
shows up at the query level (insuring against either single retriever's specific
failure) rather than in this topline number.

## Serve it

```bash
uv run uvicorn app.api:app --reload
```

- `GET /search/dense?q=...&top_k=10`
- `GET /search/sparse?q=...&top_k=10`
- `GET /search/hybrid?q=...&top_k=10`

## Test

```bash
uv run pytest
```

`tests/test_fusion.py` is pure Python (no DB) and always runs — it checks the RRF
math against the worked example in `concept.md`. `tests/test_retrieval.py` needs
the ParadeDB container up and seeds it itself via a session fixture; it's the
suite that actually demonstrates, deterministically, the failure modes concept.md
describes: BM25 missing a paraphrased query with zero token overlap, BM25 nailing
an exact-token query, and hybrid recovering/preserving both.

## Layout

```
app/
  config.py       env-driven settings (DB URL, embedding model, RRF k)
  embeddings.py   fastembed wrapper (query vs. passage prefixing)
  schema.sql      documents table + HNSW index + pg_search BM25 index
  db.py           raw SQL: dense_search (pgvector), sparse_search (pg_search)
  fusion.py       rrf_fuse() -- pure, DB-free
  retriever.py    LlamaIndex BaseRetriever subclasses (Dense/Sparse/HybridRRF)
  corpus.py       70-doc synthetic corpus + 20-query benchmark set
  ingest.py       embed + load the corpus
  benchmark.py    the recall@10 comparison
  api.py          FastAPI endpoints over the three retrievers
tests/
  test_fusion.py     RRF unit tests
  test_retrieval.py  integration tests against a live ParadeDB
```
