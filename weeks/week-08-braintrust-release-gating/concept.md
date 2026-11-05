# Week 8: Braintrust release gating + Langfuse production observability

## Overview

Weeks 5-7 built three different ways to *check* a RAG pipeline's quality and safety
offline: RAGAS metrics, DeepEval CI gates, Promptfoo red-teaming. This week asks a
different question: once those checks exist, how do they actually stop a bad change
from merging, and how do you know what's happening to the *same* pipeline once it's
serving real traffic? Those are two genuinely separate problems with two genuinely
separate categories of tool:

- **Release gating** -- a CI-time check on a candidate change, before it merges.
  Braintrust is this week's tool for it.
- **Production observability** -- a live, always-on record of every real request,
  after it's shipped. Langfuse (self-hosted) is this week's tool for it.

They share underlying concepts (traces, scores, LLM-judged metrics) but solve
different problems at different points in a change's lifecycle, and conflating them is
the single most common mistake in this space -- covered in depth below.

## Core concept, in depth

### 1. The release-gate model: dataset -> experiment -> diff -> comment

Braintrust's object model, mapped onto this week's actual files:

- **A Dataset** (`app/dataset.py`'s `GOLDENS`, pushed by `app/braintrust_push.py` via
  `init_dataset(...).insert(...)`) -- a versioned, reusable set of `{input, expected,
  metadata}` cases. This is *data*, not a result. Pushing it is a one-time/occasional
  action, not something that runs on every PR.
- **An Eval()** (`evals/eval_rag_quality.py`) -- a *task* (the function under test --
  here, `RAGPipeline.answer()` wrapped as `answer_question`) run over that dataset,
  scored by one or more *scorers* (`retrieval_hit`, `faithfulness`). Running `Eval()`
  produces an **experiment** -- one concrete, timestamped, scored run.
- **The diff** -- Braintrust automatically compares a new experiment against the base
  branch's most recent experiment for the same project. This diff, not any single
  experiment's absolute score, is what a release gate actually needs: "did this PR make
  faithfulness worse," not "is faithfulness currently 0.87."
- **The PR comment** -- `braintrustdata/eval-action` runs `Eval()` in CI and posts that
  diff as a PR comment automatically. Nothing in this project computes or formats that
  comment by hand; the gate mechanic *is* Braintrust's own experiment-diffing, surfaced
  through the action.

This week deliberately uses one deterministic scorer (`retrieval_hit`: does BM25 return
the one document this question's answer actually depends on -- free, instant, no LLM
call) and one LLM-judged scorer (`faithfulness`, RAGAS's metric: does the answer only
state things the retrieved context supports -- costs one OpenAI call per case,
non-deterministic between runs). Weeks 6 and 7 both argued for keeping a *push-time*
gate cheap and deterministic, and pushing anything LLM-judged into a slower, periodic
tier. This week's task explicitly runs the LLM-judged metric on every PR anyway --
because a *release gate* (blocks a specific candidate change from merging, runs at
PR-time, humans expect to wait a bit) has a different cost/latency budget than a
*push gate* (blocks every commit including small in-progress ones, needs to be near-
instant). Same tension as before; different point on the curve because it's gating a
different event.

### 2. The observability model: trace -> span -> generation -> score

Langfuse's object model, mapped onto `app/tracing.py`:

- **A trace** -- one real `/chat` request end to end (`rag-request` span in
  `traced_answer`).
- **Spans** -- named phases inside that trace. This project creates two: `retrieval`
  (records which doc IDs came back and BM25's top score) and `generation` (the OpenAI
  call).
- **A generation** -- a span subtype specifically for an LLM call, carrying
  `usage_details` (input/output tokens) and `cost_details` (USD), which is what makes
  token cost trackable per-request rather than just as an aggregate API bill.
- **A score** -- a number or boolean attached to a trace after the fact.
  `retrieval_hit_rate` is logged here as `1` if BM25's top score clears
  `MIN_RELEVANCE_SCORE`, else `0`.

**The crucial asymmetry vs. the eval side:** in `evals/eval_rag_quality.py`,
`retrieval_hit` is computed against real ground truth (`metadata["source_doc_id"]`,
known because the golden set is hand-labeled). In `app/tracing.py`, production traffic
has no such label -- nobody tags a live customer's question with "the correct document
is X" before asking it. So `retrieval_hit_rate` in production is a *proxy*: "did
retrieval return something it's confident about" (BM25 score above a threshold), not
"did retrieval return the actually-correct document." Same metric name, two different
things it's measuring, for the unavoidable reason that ground truth only exists in a
curated eval set, never in raw production traffic. Confusing these two is a real,
common pitfall -- see below.

### 3. Why self-hosted, and why v4's infra didn't change

The task calls for *self-hosted* Langfuse specifically (not Langfuse Cloud) --
`docker/langfuse/docker-compose.yml` runs Postgres (relational metadata), ClickHouse
(the trace/observation event store, built for high-volume analytical queries), Redis
(queueing/caching), and MinIO (S3-compatible blob storage for large trace payloads),
plus `langfuse-web` and `langfuse-worker` containers.

Langfuse shipped v4 in August 2026 with a **data-model** change, not an infrastructure
one -- confirmed directly against Langfuse's own migration docs: *"The infrastructure
architecture remains unchanged in v4, utilizing the same components as v3, including
PostgreSQL, ClickHouse, Redis, and S3."* Practically, this means the compose file here
is the same shape a v3 deployment would use, with the image tag bumped to `langfuse/
langfuse:4` / `langfuse/langfuse-worker:4` -- there's no new service to add, no service
to remove, just a data-model migration Langfuse's worker runs on top of existing
infrastructure. This is exactly why the task's flagged update matters: pointing at an
old self-hosting doc wouldn't have given wrong *infrastructure* instructions, but could
still describe an outdated upgrade/migration path if you're moving an existing v2/v3
deployment forward.

## Why it matters in production

A release gate with no diffing is just a dashboard nobody reads until something's
already broken -- the reason Braintrust's baseline-comparison mechanic matters more
than any single score is that "faithfulness is 0.84" tells a reviewer nothing on its
own; "faithfulness dropped from 0.91 to 0.84 on this PR" tells them exactly what to
look at before merging. And an observability layer with no per-request cost/retrieval
data is useless for the two questions that actually page someone at 2am: "why did our
OpenAI bill triple this week" (token cost per trace, aggregated) and "why are answers
suddenly worse" (retrieval_hit_rate dropping is visible *before* customers complain,
if a corpus reindex or embedding change silently breaks retrieval). Both tools exist
because "it passed my eval script once" and "it's been fine so far" are both
unfalsifiable without a durable, queryable record.

## Tradeoffs & comparisons

The second goal this week names explicitly: Braintrust vs. LangSmith vs. Langfuse.
All three let you trace LLM calls and score them -- the differences that actually
matter for picking one:

| | Braintrust | LangSmith | Langfuse |
|---|---|---|---|
| **Primary framing** | Eval-as-CI / release gate | Trace explorer / debugging | OSS observability platform |
| **Hosting** | Managed only | Managed (LangChain's platform) | Self-hostable (this week) or managed |
| **Core primitive** | Dataset -> Eval() -> experiment, diffed against a baseline | Trace + run tree, searchable/filterable | Trace + span + generation + score |
| **CI story** | First-class: `eval-action` posts score deltas on PRs | Possible, but framed around interactive debugging, not gating | Possible via SDK, but no built-in PR-diff mechanic |
| **Vendor coupling** | None (any framework) | Strongest ties to LangChain/LangGraph, though usable standalone | None; OTel-based Python/JS SDKs |
| **This week's role** | Blocks a PR from merging on a regression | (not used this week) | Watches every live request after merge |

The practical takeaway, and the reason this week uses two tools instead of one: a
release gate needs a *baseline to diff against* and a CI-native integration (Braintrust's
niche); production observability needs to be *always running, cheap to self-host at
volume, and queryable after the fact* (Langfuse's niche, especially self-hosted where
you control retention/cost instead of paying per-trace to a vendor). LangSmith sits
closer to Langfuse's niche but is more tightly coupled to the LangChain ecosystem and
is framed around interactive trace debugging rather than either automated gating or
self-hosted production-scale observability -- which is why this week's task doesn't
ask you to wire it in for anything, only to understand where it would fit if you were
already deep in LangChain/LangGraph.

**Two more tools worth knowing about, not used this week (research only, nothing
implemented):**

- **Pydantic Logfire** -- a full-stack, OTel-native observability platform (built by the
  Pydantic team), not LLM-specific like Langfuse. It traces the whole app (FastAPI, DB
  queries, HTTP clients) with the LLM call as one span among many, and lets you query
  trace data with plain SQL. The SDK is open source (MIT), but unlike Langfuse, the
  platform itself has **no free self-hosted tier** -- only a free *cloud* (SaaS) tier, or
  a paid Enterprise tier for self-hosting. That's the practical reason it doesn't
  replace Langfuse here: this project's self-hosting requirement (see above) is free
  with Langfuse and isn't with Logfire.
- **Arize Phoenix** -- open source and free to self-host, like Langfuse, but also
  OTel-native like Logfire, and bundles both production tracing *and* evals (datasets +
  experiments) in one tool -- closer to a free, self-hostable blend of what Langfuse and
  Braintrust do separately in this week's setup.

## Common pitfalls

- **Treating `retrieval_hit_rate` the same in both places.** The eval-side
  `retrieval_hit` (ground-truth-based) and the tracing-side `retrieval_hit_rate`
  (BM25-score-threshold proxy) answer different questions. Averaging them together, or
  assuming a change in one implies the same change in the other, is a category error --
  see "The crucial asymmetry" above.
- **Running the LLM-judged scorer on every commit instead of every PR.** `faithfulness`
  costs a real OpenAI call and is non-deterministic between runs. This week's
  `.github/workflows/week-08-braintrust-eval.yml` only triggers on `pull_request`, not
  `push` -- gating every commit with it would reintroduce exactly the cost/determinism
  problem Weeks 6-7 solved by tiering.
- **Assuming Langfuse v4 needs new infrastructure.** It doesn't -- confirmed above. The
  actual migration risk is the *data model* change (how existing traces are represented
  after upgrade), which is why the task flagged pointing at the v3->v4 migration guide
  specifically, not a general infra how-to.
- **Confusing a Dataset with an experiment.** `app/braintrust_push.py` pushes a
  *Dataset* (reusable input data, versioned, no scores). `evals/eval_rag_quality.py`
  running `Eval()` produces an *experiment* (one scored run over that data). Re-running
  `braintrust_push.py` should upsert the same rows, not create new datasets; re-running
  the eval file always creates a new experiment, by design, since each PR needs its
  own to diff against the baseline.
- **Assuming a GitHub Action's undocumented behavior.** This project's own workflow
  file (`.github/workflows/week-08-braintrust-eval.yml`) flags an unconfirmed detail
  (whether `eval-action` needs an explicit path input to find `evals/` inside a
  monorepo subdirectory) rather than guessing past it -- worth noticing as a pattern:
  verify a third-party action's actual input schema before depending on inferred
  behavior in a real CI gate.

## Check yourself

1. Why does `evals/eval_rag_quality.py`'s `retrieval_hit` scorer have access to ground
   truth (`source_doc_id`) that `app/tracing.py`'s `retrieval_hit_rate` score doesn't?
   What would it take to compute a true, ground-truth-based hit rate on live traffic?
2. If Braintrust's `eval-action` only diffs against "the base branch's most recent
   experiment," what has to be true about *when* experiments get logged on the base
   branch for that diff to mean anything on a PR?
3. Why is it fine for `faithfulness` to be non-deterministic between two runs of the
   exact same PR, but not fine for the CI gate's pass/fail *decision* to flip between
   runs? (Hint: think about what Braintrust's diff is actually thresholding on, vs.
   what a hand-written `assert score > 0.8` would do.)
4. `app/tracing.py`'s generation span logs `cost_details` computed from a hardcoded
   $/token constant. What breaks first if `OPENAI_MODEL` changes to a different-priced
   model, and where's the more correct place to source that price?
5. Langfuse's self-hosting docs say v4's infrastructure requirements are identical to
   v3's. Given that, what's actually risky about an in-place v3->v4 upgrade, if not
   "which containers do I need to add"?
