# Chunking Strategies & Embedding Model Selection

Week 1b project: six chunking strategies (fixed-size, sentence-window,
recursive character, semantic, AST-aware, and Late Chunking) compared with
NDCG@10 on a fixed embedding model, then three MTEB-shortlisted embedding
models crossed against all six strategies (18 combinations) and measured
with recall@10, on a real ~500-document code+text corpus. See
[`../concept.md`](../concept.md) for the theory this implements.

## Install

```bash
uv sync
```

## The corpus

`data/corpus.jsonl` (checked in, ~526 real documents) is built once by
`app/build_corpus.py` from two real sources, not synthetic text:

- **Code half** (259 docs): real, non-test `.py` files from `requests`,
  `click`, `jinja`, `gunicorn`, `flask`, `werkzeug`, and `black` — small,
  well-known open source repos, shallow-cloned.
- **Text half** (267 docs): real chapters/stories from 9 public-domain
  Gutenberg books (*The Adventures of Sherlock Holmes*, *Alice's Adventures
  in Wonderland*, *The Wonderful Wizard of Oz*, *Treasure Island*, *Anne of
  Green Gables*, *Pride and Prejudice*, *Frankenstein*, *The Secret
  Garden*, *Little Women*), split on each book's actual chapter-heading
  convention (they're not uniform -- see `build_corpus.py`'s `BOOKS`
  config).

Re-running `build_corpus.py` requires the source repos/books to be
re-fetched (it reads from a scratch directory, not checked into this repo)
-- the committed `data/corpus.jsonl` is the artifact that matters; you
don't need to regenerate it to run the benchmarks.

## The query set

20 queries in `app/corpus.py` (10 text, 10 code), each with hand-verified
ground truth: text queries paraphrase a real Sherlock Holmes story's plot
(without reusing its title), code queries paraphrase what a real, specific
function/class in one of the cloned repos actually does -- checked against
its real docstring before being written, not guessed from memory. See the
module docstring in `app/corpus.py`.

## Run Part 1: chunking strategy comparison

```bash
uv run python -m app.run_strategy_comparison
```

Holds the embedding model fixed (`nomic-ai/modernbert-embed-base` -- the
only shortlisted model with a long enough context window to let Late
Chunking do anything meaningful) and compares all 6 strategies with
NDCG@10. Writes `data/part1_strategy_comparison.json`.

## Run Part 2: model x strategy grid

```bash
uv run python -m app.run_model_strategy_grid
```

Runs all 3 models x 6 strategies = 18 combinations, measures recall@10 for
each, prints the full grid, and **overwrites `app/config.py`** with the
winning combination as `DEFAULT_CHUNKING_STRATEGY` /
`DEFAULT_EMBEDDING_MODEL` -- the "hard-code the winner as the pipeline
default for subsequent weeks" task. Writes
`data/part2_model_strategy_grid.json`.

## W&B logging

Every run in both scripts logs `chunking_strategy` and `embedding_model` as
W&B run config (`app/wandb_logging.py`), plus its measured metrics. Runs
offline by default (writes to `./wandb/`, no account needed) since this
environment has no `WANDB_API_KEY`:

```bash
wandb login
wandb sync wandb/offline-run-*   # push the offline runs to your project
```

Set `WANDB_MODE=online` (with `WANDB_API_KEY` set) to log live instead.

## Results

*(See [`../concept.md`](../concept.md)'s "Measured results on this corpus"
section and the two `data/part*.json` files for the full numbers.)*

## Run tests

```bash
uv run pytest
```

`test_metrics.py` and `test_corpus.py` are fast/pure. `test_chunkers.py`
hits real Chonkie chunkers and a real (small, already-cached) model --
still fast, but not mocked, so it catches real Chonkie/transformers API
drift.
