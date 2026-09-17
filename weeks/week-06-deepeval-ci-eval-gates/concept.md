# Week 6: DeepEval and CI Eval Gates

## Overview

Week 5 built a RAGAS metric suite and ran it by hand (`uv run python runner.py`) whenever
you felt like checking quality. That's fine for exploration, but it doesn't stop a bad
change from shipping -- nothing forces the check to run, and nothing blocks a merge when
scores drop. This week turns evaluation into a **gate**: the same kind of metrics (now
via DeepEval instead of RAGAS), wired into `pytest` so they run automatically on every
push, with explicit pass/fail thresholds a CI pipeline can act on. The shift isn't really
about DeepEval vs. RAGAS as libraries -- it's about turning "evaluation" from a report you
read into a check that can say no.

## Core concept, in depth

### DeepEval's test-case model

DeepEval represents one thing-to-evaluate as an `LLMTestCase` -- a plain data object with
up to nine fields, of which only `input` is ever required. The RAG-relevant ones:

| `LLMTestCase` field | What it holds | RAGAS's equivalent name |
|---|---|---|
| `input` | the user's question | `user_input` |
| `actual_output` | what your pipeline actually generated | `response` |
| `retrieval_context` | the chunks your retriever returned | `retrieved_contexts` |
| `expected_output` | the ground-truth/reference answer | `reference` |

That table is the entire "conversion" the weekly task asks for: RAGAS and DeepEval model
the exact same RAG evaluation shape (question, generated answer, retrieved context,
reference answer) under different field names. Converting a RAGAS-style dataset into
DeepEval test cases is a renaming exercise, not a redesign -- see
`app/deepeval_cases.py`'s `sample_to_test_case()` for the actual mapping.

Each **metric** is an object (`FaithfulnessMetric()`, `AnswerRelevancyMetric()`,
`ContextualRecallMetric()`, ...) that takes a `threshold`, a judge `model`, and declares
which `LLMTestCase` fields it needs:

- **Faithfulness** needs `input`, `actual_output`, `retrieval_context` -- no reference
  required. It checks whether claims in `actual_output` are actually supported by
  `retrieval_context` (same "is a person reading only my answer" here in Week 5).
- **Answer Relevancy** needs only `input` and `actual_output` -- also reference-free. Same
  underlying idea as RAGAS's version: does the answer actually address the question.
- **Contextual Recall** needs `input`, `actual_output`, `expected_output`, and
  `retrieval_context` -- it *does* need a reference, because it's asking "did retrieval
  bring back everything needed to produce the reference answer?" (RAGAS's Context Recall,
  same question, same requirement).

### LLM-as-judge, concretely

All three metrics above are **not** computed by a formula over the text -- they're
computed by asking another LLM to read the test case and score it. `model="gpt-4o-mini"`
(or `"gpt-4o"`, or a Claude wrapper via DeepEval's `DeepEvalBaseLLM` interface) is that
judge. Concretely, `FaithfulnessMetric.measure()` runs (roughly) two judge calls under the
hood: one that decomposes `actual_output` into individual factual claims, and one that
checks each claim against `retrieval_context`, then produces a 0-1 score plus, if
`include_reason=True`, a natural-language justification.

This is exactly what makes LLM-as-judge powerful and risky in the same breath:
- **Powerful**: it can judge things no formula can -- "is this claim actually supported by
  that paragraph" requires reading comprehension, not string matching.
- **Risky**: the judge is itself a model with its own biases, occasional
  misjudgments, and non-zero variance run-to-run (ask the same question twice, get
  slightly different scores). It also costs money and latency per test case, which is the
  whole reason CI-gate datasets stay small and fixed (see below) rather than mirroring
  Week 5's full 50-sample benchmark.

`assert_test(test_case, metrics)` is the bridge into `pytest`: it runs every metric
against the test case and raises `AssertionError` the moment one falls under its
`threshold` -- which is exactly how a plain `assert` statement in any other test would
fail a build.

### Why the CI dataset is small and fixed, not regenerated

Week 5's dataset mixed 10 hand-labeled samples with 40 LLM-synthesized ones, regenerated
by calling `OPENAI_MODEL` at eval time. That's the right shape for a periodic, thorough
benchmark run. It's the *wrong* shape for a gate that runs on every `git push`:

- Regenerating synthetic goldens via an LLM call on every push adds cost and latency to
  *every commit*, not just eval runs.
- It also makes the gate itself non-deterministic -- the questions being tested change
  from run to run, so "did my change break something" and "did the synthetic generator
  phrase this batch differently" become impossible to tell apart.

So this week's dataset (`app/dataset.py`) is a small, fixed, hand-written set of goldens
-- the same shape as Week 5's `HAND_LABELED`, but treated as the *entire* fixture, not a
seed for synthetic expansion. This is a real production pattern: a small, curated,
version-controlled "golden set" for the fast gate that runs constantly, separate from a
larger, sampled or synthetic benchmark that runs less often (nightly, weekly) to catch
slower drift.

### The CI mechanics

`deepeval test run tests/test_rag_quality.py` (or plain `pytest`, since `assert_test`
degrades to a normal `pytest` assertion) runs the parametrized test, one `LLMTestCase`
per golden, three metrics each. A GitHub Actions workflow triggers on `push`, runs that
command with `OPENAI_API_KEY` from repo secrets, and the job's exit code *is* the merge
gate -- a nonzero exit from a failed `assert_test` fails the workflow run, which is what a
branch protection rule ("require status checks to pass") turns into an actual block on
merging.

## Why it matters in production

Every RAG system degrades silently without something like this: someone changes a chunk
size, swaps an embedding model, tweaks a prompt, or a dependency bumps a default, and
retrieval quality quietly drops. Nobody notices until a support ticket says the bot gave a
wrong answer -- by which point it's been wrong for however long since the change shipped.
An eval gate turns that into a build failure at the moment the regression is introduced,
with the diff that caused it sitting right there in the same PR. That's the entire value
proposition of "unit tests for LLM apps" -- catching in CI what would otherwise surface in
production, days or weeks later, disconnected from its cause.

## Tradeoffs & comparisons

**DeepEval vs. RAGAS**: functionally overlapping (both compute LLM-judged RAG metrics
with near-identical definitions), but they optimize for different moments. RAGAS reads
like a benchmarking/research library -- built around `evaluate()` over a whole dataset,
producing a report. DeepEval is built assertion-first -- `assert_test()` inside `pytest`,
a first-class CLI runner (`deepeval test run`) with CI ergonomics (`--exit-on-first-failure`,
caching, identifiers per run), and metrics designed to be pass/fail thresholds rather than
scores to eyeball. Using RAGAS for periodic deep benchmarking and DeepEval for the CI gate
-- as this and Week 5 now do -- plays to each library's actual design center.

**Fixed thresholds vs. drop-from-baseline**: this week hardcodes absolute thresholds
(Faithfulness ≥ 0.8, etc.), which is simple and legible but arbitrary -- why 0.8 and not
0.75? A more mature setup tracks a rolling baseline (e.g. via W&B, which is why it's in
this week's toolset) and fails when a metric drops more than some delta from that
baseline, catching regressions even in the range where an absolute threshold wouldn't
trip.

**Reference-required vs. reference-free metrics**: Faithfulness and Answer Relevancy
don't need `expected_output`; Contextual Recall does. That asymmetry from Week 5 carries
over unchanged -- it's a property of what each metric measures, not of which library
computes it.

## Common pitfalls

- **Testing the LLM's mood, not your code.** LLM-as-judge scores have run-to-run variance.
  A flaky test that fails 1-in-20 runs erodes trust in the whole gate fast -- teams start
  ignoring red CI, which defeats the point. Set thresholds with headroom, and consider
  `--repeat`/majority-vote patterns for genuinely borderline metrics.
- **Letting the CI dataset grow into a full benchmark.** Every golden added to the CI
  suite is judge-model cost and latency on *every push*. Keep the gate's dataset small and
  targeted; put breadth in a separate, less-frequent benchmark job.
- **Forgetting the judge needs credentials in CI too.** The workflow needs
  `OPENAI_API_KEY` (or your judge provider's key) in repo secrets -- a PR from a fork
  won't have access to secrets by default, which is a legitimate GitHub Actions security
  boundary, not a bug, but it does mean fork PRs won't get real eval results without
  extra workflow configuration.
- **Conflating "retrieval got worse" with "the judge is wrong."** When a threshold trips,
  read `metric.reason` (from `include_reason=True`) before assuming the judge
  misjudged -- often it's caught something real.

## Check yourself

1. Which of this week's three metrics need `expected_output`, and why does that one in
   particular need it while the other two don't?
2. If you renamed RAGAS's `user_input`/`response`/`retrieved_contexts`/`reference` to
   DeepEval's `input`/`actual_output`/`retrieval_context`/`expected_output`, would any
   RAG evaluation *logic* actually need to change? What does that tell you about how
   portable an eval dataset is across frameworks?
3. Why does this week's CI dataset stay small and fixed instead of reusing Week 5's
   pattern of expanding with LLM-synthesized samples?
4. `assert_test` raises `AssertionError` on failure. Trace the chain from that exception
   to a blocked merge: what has to be true about the pytest exit code, the GitHub Actions
   job, and the branch protection rule for that block to actually happen?
5. Faithfulness and Contextual Recall can both be low for the *same* bad answer, for two
   different reasons. What's the difference between "unfaithful" and "poor context
   recall" as failure modes, and which one points you at the retriever vs. the generator?
