# Week 5 — RAGAS: RAG-Specific Evaluation Metrics

A small standalone retrieve-then-generate pipeline (`app/pipeline.py`, BM25 retrieval
+ OpenAI generation) over a fixed 10-document corpus (`app/corpus.py`), evaluated with
the full RAGAS metric suite: Faithfulness, Answer Relevancy, Context Precision,
Context Recall, Answer/Semantic Similarity, and Answer Correctness.

See [concept.md](../concept.md) for what each metric actually measures and why the
reference-free/reference-based split matters.

## Install

```bash
uv sync
```

Retrieval (BM25) needs no API key and works offline. Everything else -- pipeline
generation, synthetic dataset generation, and RAGAS's LLM-judged metrics -- needs a
real OpenAI key:

```bash
export OPENAI_API_KEY=sk-...
```

Without it, `runner.py` and every OpenAI-dependent test skip cleanly rather than
failing (see `tests/conftest.py`'s `requires_openai` marker).

## Run the debug script

```bash
uv run python runner.py                    # 10 hand-labeled samples (cheap, fast)
INCLUDE_SYNTHETIC=1 uv run python runner.py # full 50-sample set (10 hand + 40 GPT-4o-synthetic)
```

Prints every metric's score, flags the weakest one, and logs the run to W&B (offline
by default -- see `./wandb/` after running; `wandb login && wandb sync wandb/offline-run-*`
pushes it to the cloud).

`OPENAI_MODEL` (default `gpt-4o-mini`) controls both the pipeline's generator and
RAGAS's judge model; set it to `gpt-4o` to match the roadmap task's literal tool list
at higher cost.

## Run tests

```bash
uv run pytest -v
```

Structural tests (corpus, retrieval, dataset shape, `_build_dataset`) run with no API
key. Tests marked `requires_openai` make small, deliberately minimal real API calls
(e.g. evaluating just 2 samples, generating just 2 synthetic pairs) and skip cleanly
if `OPENAI_API_KEY` isn't set.

## Project layout

- `app/corpus.py` — fixed 10-passage documentation corpus.
- `app/retrieval.py` — BM25 retrieval (no API cost).
- `app/llm.py` — OpenAI generation wrapper, gated behind `OPENAI_API_KEY`.
- `app/pipeline.py` — the pipeline under evaluation (retrieve + generate).
- `app/dataset.py` — 10 hand-labeled samples + `generate_synthetic_samples()` (GPT-4o).
- `app/metrics.py` — resolves the 6 RAGAS metrics against whichever API shape the
  installed `ragas` version exposes (see concept.md's Common Pitfalls — this is not
  hypothetical, RAGAS's metric API has genuinely moved across versions).
- `app/evaluate.py` — runs the pipeline over a dataset, scores it, finds the weakest metric.
- `app/wandb_logging.py` — logs a run as a W&B baseline experiment.
- `runner.py` — standalone debug entry point.
