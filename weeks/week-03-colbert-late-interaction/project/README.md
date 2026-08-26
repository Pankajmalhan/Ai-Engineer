# ColBERT Late-Interaction Retrieval (RAGatouille + PLAID)

Week 3 project: a real ColBERT/PLAID index, built over a live Wikipedia
corpus, used as a **complete, standalone first-stage retriever** (not a
reranker sitting on top of anything else -- see
[`../concept.md`](../concept.md) for why that's the point). A single-vector
bi-encoder runs as a separate, independent baseline over the same corpus so
`app/compare.py` can measure ColBERT's token-level MaxSim scoring against
plain cosine similarity on compositional, multi-hop queries.

## Install

```bash
uv sync
```

This project pins three dependencies to versions older than their current
releases -- `ragatouille<0.0.10`, `langchain<1.0`, `transformers<4.50` --
plus an undeclared transitive dependency (`psutil`). All three constraints
were discovered by actually running this project against current package
releases, not guessed ahead of time; see the comments in
[`pyproject.toml`](pyproject.toml) and `concept.md`'s "Common pitfalls" for
what breaks without each one.

## Build the ColBERT/PLAID index

```bash
uv run python -m app.index
```

Fetches ~60 Wikipedia articles (cached to `data/wikipedia_cache.json` after
the first run, so this only hits the network once), splits them into
~256-token passages, encodes every passage through `colbert-ir/colbertv2.0`
(one 128-dim vector per token), and builds a PLAID index under
`.ragatouille/colbert/indexes/week3_wikipedia/`. On a CPU-only laptop this
takes a few minutes -- most of the time is the encoding pass, not the
clustering step. Writes `data/index_stats.json` with the real article and
passage counts once done.

**Note on `ARTICLE_LIMIT`**: the roadmap task asks for a 5,000-passage
index; this project defaults to a smaller `ARTICLE_LIMIT=60` (~2,800
passages after splitting) so a full run finishes in minutes rather than
tens of minutes on CPU. Raise it via `ARTICLE_LIMIT=200 uv run python -m
app.index` (more `DISTRACTOR_TITLES` would need adding to `app/corpus.py`
past a point) to scale closer to the full target -- the indexing and
search code is identical either way, only the wall-clock cost changes.

## Build the bi-encoder baseline

```bash
uv run python -m app.baseline
```

Embeds the *same* passages (same chunker, same boundaries as the ColBERT
index, via `ragatouille`'s own `llama_index_sentence_splitter`) with
`BAAI/bge-small-en-v1.5`, mean-pooled to one vector each, saved to
`data/baseline_embeddings.npy` + `data/baseline_passages.json`. This is a
completely independent pipeline from the ColBERT index -- neither one
reranks or feeds into the other; see `concept.md` and this week's
conversation on why that distinction matters.

## Compare ColBERT vs. the bi-encoder on multi-hop queries

```bash
uv run python -m app.compare
```

Runs `MULTIHOP_QUERIES` (`app/corpus.py`) -- five compositional questions
that need two or more distinct facts satisfied at once (e.g. "who directed
Spirited Away and what other studio did they co-found") -- through both
pipelines independently, and reports how often each side's top-k results
include the query's actually-relevant articles. Writes
`data/compare_results.json` with the full per-query breakdown.

## Profile index size: per-token vs. per-document storage

```bash
uv run python -m app.profile_index
```

Measures, on this corpus, what "one 128-dim vector per token" actually
costs on disk: an uncompressed estimate, PLAID's real compressed size, and
the bi-encoder's actual single-vector index size, side by side. Requires
both the ColBERT index and the baseline embeddings to already exist. Writes
`data/index_profile.json`.

## Test

```bash
uv run pytest
```

- `tests/test_corpus.py` -- pure, no network (fetches are monkeypatched),
  no model. Always runs.
- `tests/test_compare.py`, `tests/test_profile_index.py` -- pure logic/math
  helpers, no model, no index. Always run.
- `tests/test_colbert_index.py` -- real, end-to-end: builds a tiny 3-sentence
  ColBERT/PLAID index with the actual `colbert-ir/colbertv2.0` checkpoint
  (not mocked) and checks MaxSim ranks the genuinely relevant sentence
  first. Downloads the checkpoint on first run only (cached under
  `~/.cache/huggingface` after that); toy-scale, so it stays fast.

## Layout

```text
app/
  config.py         env-driven settings (checkpoint name, index name, bi-encoder model, top-k)
  corpus.py         Wikipedia fetch+cache, multi-hop query set, distractor titles
  index.py          builds the ColBERT/PLAID index (app.index)
  baseline.py       builds the bi-encoder baseline embeddings (app.baseline)
  compare.py        multi-hop A/B: ColBERT MaxSim vs. bi-encoder cosine (app.compare)
  profile_index.py  per-token vs. per-document storage cost, measured on disk (app.profile_index)
tests/
  test_corpus.py         fetch/cache logic, multi-hop query-set sanity
  test_colbert_index.py  real toy-scale ColBERT/PLAID round trip
  test_compare.py        _hits() top-k matching logic
  test_profile_index.py  storage math helpers
```
