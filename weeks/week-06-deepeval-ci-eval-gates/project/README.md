# Week 6: DeepEval and CI Eval Gates

The same small retrieve-then-generate RAG pipeline as Week 5 (BM25 retrieval, OpenAI
generation, fictional "Northwind API" docs corpus), evaluated with
[DeepEval](https://github.com/confident-ai/deepeval) instead of RAGAS -- as `pytest`
assertions with real pass/fail thresholds, wired into a GitHub Actions workflow that
fails the build on a regression.

See [`../concept.md`](../concept.md) for how this all fits together and why the CI
dataset is deliberately small and fixed rather than Week 5's larger sampled set.

## What's here

- `app/dataset.py` -- 8 fixed, hand-written goldens (question + reference answer)
- `app/pipeline.py`, `app/retrieval.py`, `app/llm.py`, `app/corpus.py` -- the RAG
  pipeline being evaluated (same shape as Week 5's)
- `app/deepeval_cases.py` -- converts each golden into a `deepeval.test_case.LLMTestCase`
  by actually running the pipeline (the "convert the RAGAS dataset into DeepEval test
  cases" task)
- `tests/test_rag_quality.py` -- the actual eval gate: `assert_test` against
  `FaithfulnessMetric` (≥ 0.8), `AnswerRelevancyMetric` (≥ 0.75), and
  `ContextualRecallMetric` (≥ 0.7)
- `runner.py` -- standalone script that prints per-metric scores and logs them to W&B
  (offline by default); doesn't fail/exit nonzero, unlike the pytest gate
- `../../.github/workflows/week-06-deepeval-eval-gates.yml` (repo root, since GitHub
  Actions only reads workflows from there) -- runs the eval suite on every push

## Install

```bash
uv sync
```

## Run

```bash
export OPENAI_API_KEY=sk-...

# Full test suite (structural tests always run; the real eval gate needs the key above)
uv run pytest tests/ -v

# Or via DeepEval's own CLI runner (adds -x/--repeat/caching/etc, same underlying pytest)
uv run deepeval test run tests/test_rag_quality.py

# Print per-metric scores + log to W&B, without gating
uv run python runner.py
```

Without `OPENAI_API_KEY` set, the structural tests (`test_deepeval_cases.py`,
`test_retrieval.py`) still run and pass; `test_rag_quality.py`'s real eval gate skips
cleanly with an explicit reason instead of erroring or silently vanishing.

## Reproduce "push a deliberately bad change"

`app/retrieval.py`'s `BM25Retriever` has a `BREAK_RETRIEVAL` toggle that returns the
**least** relevant chunks instead of the most relevant ones -- a stand-in for a real
retrieval regression (broken index, swapped embedding model, ...).

```bash
BREAK_RETRIEVAL=1 uv run pytest tests/test_rag_quality.py -v
```

With wrong chunks retrieved, Faithfulness and Contextual Recall should drop below
threshold and `assert_test` should raise -- exactly what fails the GitHub Actions job on
a real push. Revert (unset `BREAK_RETRIEVAL` / remove the commit) to confirm it goes
back to passing.

## GitHub Actions

The workflow at the repo root (`.github/workflows/week-06-deepeval-eval-gates.yml`)
triggers on every push and on PRs into `main`, path-filtered to this project. It needs
an `OPENAI_API_KEY` repository secret to actually run the judge calls. To make it a real
merge gate, add it as a required status check under the repo's branch protection rules
for `main`.
