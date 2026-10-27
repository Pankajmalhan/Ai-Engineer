# Week 8 project: Braintrust release gate + Langfuse observability

The Northwind API RAG service (same fixture corpus as Weeks 5-7), with two eval/observability
layers added on top:

- **Braintrust** -- an eval-as-CI release gate. `evals/eval_rag_quality.py` scores every PR's
  pipeline against a fixed golden set with a deterministic `retrieval_hit` score and RAGAS's
  LLM-judged `faithfulness` score, logging a new Braintrust *experiment* each run. Braintrust
  diffs that experiment against the base branch's and the `braintrustdata/eval-action` posts
  the score delta as a PR comment.
- **Langfuse** -- self-hosted production observability. `app/tracing.py` wraps every `/chat`
  request in a trace with nested retrieval/generation spans, logs OpenAI token usage and cost
  on the generation span, and logs a `retrieval_hit_rate` score per request.

## Install

```bash
uv sync
```

## Run the service

```bash
export OPENAI_API_KEY=sk-...
uv run uvicorn app.main:app --port 8000
```

Langfuse tracing only activates if `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` are also
set (see `docker/langfuse/` to self-host and get those). Without them, `/chat` behaves
identically, just untraced -- `app/tracing.py`'s `langfuse_enabled()` gate.

## Tests

```bash
uv run pytest tests/ -v
```

All tests are structural/mocked -- no `OPENAI_API_KEY`, `BRAINTRUST_API_KEY`,
`LANGFUSE_*` keys, or running server needed.

## Push the RAGAS dataset to Braintrust (one-time / as it changes)

```bash
export BRAINTRUST_API_KEY=sk-...
uv run python -m app.braintrust_push
```

This is an account action -- sign up at braintrust.dev first. Requires a real
`BRAINTRUST_API_KEY`; `app/braintrust_push.py`'s `braintrust_available()` raises a clear
error rather than silently no-op-ing if it's missing.

## Run the Braintrust eval locally

```bash
export BRAINTRUST_API_KEY=sk-...
export OPENAI_API_KEY=sk-...
npx braintrust eval evals/
```

In CI, `.github/workflows/week-08-braintrust-eval.yml` runs this same eval file via
`braintrustdata/eval-action` on every PR and posts the score delta as a PR comment --
see that file's comments for one open unknown (whether the action needs an explicit
path input to find `evals/` inside this monorepo subdirectory) that needs confirming
against Braintrust's own docs before this is relied on as-is.

## Self-host Langfuse (v4)

```bash
cd docker/langfuse
cp .env.example .env   # fill in ENCRYPTION_KEY at minimum: openssl rand -hex 32
docker compose up -d
open http://localhost:3000
```

This brings up 6 containers (Postgres, ClickHouse, Redis, MinIO, langfuse-worker,
langfuse-web) and pulls several GB of images on first run -- not run automatically as
part of scaffolding this week. See `concept.md` for why v4's infra is identical to v3's
(this is a data-model change, not an infra rewrite).

Once running, set on the RAG service's environment:

```bash
export LANGFUSE_PUBLIC_KEY=pk-lf-...   # from the Langfuse UI, Settings > API Keys
export LANGFUSE_SECRET_KEY=sk-lf-...
export LANGFUSE_HOST=http://localhost:3000
```
