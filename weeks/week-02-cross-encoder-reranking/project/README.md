# Cross-Encoder Reranking (Cohere Rerank + BGE Reranker)

Week 2 project: a two-stage retrieval pipeline. Stage 1 is Week 1's hybrid
retriever (pgvector dense + pg_search BM25, fused with RRF) unchanged; Stage
2 reranks that pool with a cross-encoder, either Cohere's managed Rerank API
or a locally-hosted BGE reranker via `sentence-transformers`. See
[`../concept.md`](../concept.md) for the theory this implements.

This is a **separate ParadeDB container from Week 1's** (port `5434`
instead of `5433`, its own volume) so the two weeks' projects don't collide
if both are up at once — you don't need Week 1's project running or even
checked out; the corpus and query set are copied into `app/corpus.py` here.

## Install

```bash
uv sync
```

## Run Postgres (pgvector + pg_search)

```bash
docker compose up -d
```

Starts ParadeDB on `localhost:5434`. If this is your first time running
anything in this repo today, make sure Docker Desktop is actually running
first (`open -a Docker`, wait ~20s) — `docker compose up -d` will hang on a
connection error otherwise.

```bash
cp .env.example .env
```

`.env` is loaded automatically (`app/config.py` calls `load_dotenv()`), so
edit it directly rather than exporting variables by hand.

## Set up Cohere (optional)

The benchmark and tests run completely fine without this — the Cohere
column is skipped with a printed note, and BGE (which needs no API key)
still runs. To include Cohere in the comparison:

1. Get a free trial key at <https://dashboard.cohere.com/api-keys> (no
   credit card required; trial keys are rate-limited but far more than
   enough for a 25-query benchmark).
2. Put it in `.env` as `COHERE_API_KEY=...`.

## Ingest the benchmark corpus

```bash
uv run python -m app.ingest
```

Embeds and loads the same 80-document corpus Week 1 used (see
`app/corpus.py`'s docstring — it's carried over verbatim so this week's
comparison is against the same pipeline, not a different one).

## Run the A/B benchmark

```bash
uv run python -m app.benchmark
```

For each of the 25 benchmark queries: runs Stage 1 (hybrid RRF) once to get
a 25-candidate pool (`RERANK_POOL_SIZE`), then reranks that *same* pool with
each available reranker down to a final top 10 (`FINAL_TOP_K`), and reports
NDCG@10 and added latency per reranker, plus the per-query breakdown. Also
writes `data/benchmark_results.json`.

**Measured on this corpus** (BGE reranker; Cohere requires an API key — add
one to `.env` to include it in your own run, see above):

| reranker | mean NDCG@10 | recall@10 | mean latency added |
|---|---|---|---|
| no-rerank (hybrid only, baseline) | 0.910 | 96% | 0.0 ms |
| bge-reranker-base | 0.945 (+0.035) | 100% | +166.2 ms/query |

Recall@10 moved from 96%→100% (BGE recovered the one query Week 1's hybrid
retriever missed entirely — see `concept.md`'s worked example), but NDCG@10
improved by more than that recall change alone would suggest, because
reranking also moved several already-recalled documents closer to rank 1.
One query regressed (an exact-token match got reranked from rank 1 to rank
3) — see `concept.md`'s "Common pitfalls" for why average lift alone can
hide that, and check `data/benchmark_results.json`'s `per_query` array for
the full breakdown.

## Test

```bash
uv run pytest
```

- `tests/test_fusion.py`, `tests/test_metrics.py` — pure Python, no DB, no
  model download, always run.
- `tests/test_rerankers.py` — `NoOpReranker` and the
  `COHERE_API_KEY`-missing guard are pure and always run.
  `test_bge_reranker_*` hits the real local cross-encoder (not mocked) and
  downloads `BAAI/bge-reranker-base` (~1.1GB) on first run only — expect the
  first `pytest` run to take a few minutes; it's cached under
  `~/.cache/huggingface` after that. The one Cohere integration test is
  skipped automatically unless `COHERE_API_KEY` is set.
- `tests/test_retrieval.py` — needs the ParadeDB container up (`docker
  compose up -d`) and seeds it itself via a session fixture, same pattern as
  Week 1.

## Layout

```
app/
  config.py       env-driven settings (DB URL, rerank pool/top-k sizes, API keys)
  corpus.py       80-doc corpus + 25-query benchmark set, copied from Week 1
  embeddings.py   fastembed wrapper (query vs. passage prefixing) -- from Week 1
  schema.sql      documents table + HNSW index + pg_search BM25 index -- from Week 1
  db.py           raw SQL: dense_search (pgvector), sparse_search (pg_search) -- from Week 1
  fusion.py       rrf_fuse() -- from Week 1
  retriever.py    Stage 1: HybridRRFRetriever + hybrid_candidates() helper
  rerankers.py    Stage 2: CohereReranker, BGEReranker, NoOpReranker (shared interface)
  metrics.py      ndcg_at_k(), recall_at_k()
  ingest.py       embed + load the corpus
  benchmark.py    the NDCG@10 / latency A/B comparison
tests/
  test_fusion.py      RRF unit tests (from Week 1)
  test_metrics.py     NDCG@10 unit tests
  test_rerankers.py   reranker unit tests (NoOp always; BGE real, real model; Cohere skipped w/o key)
  test_retrieval.py   integration tests against a live ParadeDB
```
