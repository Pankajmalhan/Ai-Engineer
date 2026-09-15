# Week 5 — RAGAS: RAG-Specific Evaluation Metrics

## Overview

Every prior week in this roadmap improved *some* piece of a RAG pipeline — hybrid
retrieval, reranking, late interaction, corrective routing, clean ingestion — but none
of them answered "did that change actually make the system better?" with a number you
could put in a CI gate. Eyeballing a handful of outputs doesn't scale, and "the LLM's
answer looked fine to me" is not a regression test. **RAGAS** (Retrieval-Augmented
Generation Assessment) is a metric suite purpose-built for RAG: instead of one generic
"is this text good" score, it separates *retrieval quality* from *generation quality*
and further separates "is the answer grounded in what was retrieved" from "does the
answer match what a human expert would say." That separation is the whole point — a
RAG pipeline can fail in either half independently (great retrieval + a generator that
ignores the context and hallucinates; or a generator that's perfectly faithful to
context that was never relevant in the first place), and a single blended score hides
which one broke.

## Core concept, in depth

### The six metrics, and the axis that actually organizes them

The most important distinction in RAGAS is **reference-free vs. reference-based** —
whether a metric needs a ground-truth answer (`reference`, sometimes called
`ground_truth`) to compute, or only the question, the retrieved context, and the
generated response.

**Reference-free (no ground truth needed — can run on live production traffic):**

- **Faithfulness** — does the generated response actually follow from the retrieved
  context, or did the model add unsupported claims? Computed by decomposing the
  response into individual factual statements (an LLM call), then checking each
  statement for whether it can be inferred from the retrieved context (another LLM
  call, essentially an NLI/entailment judgment per statement). Score = (statements
  supported by context) / (total statements). A response can be 100% faithful and
  still be *wrong* — faithfulness measures groundedness in context, not truth against
  the real world. A correct fact the model already knew, that wasn't in the retrieved
  context, still counts as unfaithful. This is intentional: it's measuring whether
  your retrieval pipeline is doing the work, not whether the LLM is generally smart.
- **Answer Relevancy** (current stable-docs class name: `AnswerRelevancy`, imported
  from `ragas.metrics.collections`; this exact name has moved at least twice — see
  Common Pitfalls) — does the response actually address the question asked, without
  padding or drifting off-topic? Computed by having the LLM generate several
  *hypothetical questions* that the response would answer, embedding each, and
  averaging their cosine similarity to the embedding of the original question. A
  response that's faithful to context but answers a different question than the one
  asked scores low here even though Faithfulness might score high — this is exactly
  why the two are separate metrics.
- **Context Precision** — of the chunks retrieved, how many were actually useful,
  and were the useful ones ranked near the top? RAGAS ships both a reference-based
  variant (judges each retrieved chunk's relevance against the `reference` answer) and
  a reference-free variant (judges relevance against the `response` instead) — same
  metric name, two different signals depending on which columns your dataset
  provides. Under the hood it's a precision@k-style computation: for each rank
  position, was that chunk relevant, weighted so relevant chunks retrieved earlier
  contribute more (similar in spirit to Average Precision from classic IR).

**Reference-based (need a `reference`/ground-truth answer — this is what the 50-sample
hand-labeled+synthetic dataset in this week's task is for):**

- **Context Recall** — of everything in the ground-truth answer, how much of that
  information was actually present *somewhere* in the retrieved contexts? Computed by
  breaking the `reference` into individual claims and checking, per claim, whether it's
  attributable to the retrieved contexts. This is the metric that catches "the answer
  is right but only because the model already knew it, not because retrieval found the
  supporting document" — a high Faithfulness + low Context Recall combination is a
  real, specific failure signature (see Common Pitfalls).
- **Answer Similarity** (current docs list this as **Semantic Similarity**, replacing
  the older `answer_similarity` name — another instance of the metric-renaming pattern
  this week's resources flagged) — pure embedding cosine similarity between the
  generated response and the reference answer. No LLM judge call, just an embedding
  model, which makes it the cheapest and most deterministic of the six.
- **Answer Correctness** — the most composite metric: blends semantic similarity
  (does it *read* like the reference) with factual overlap (precision/recall of atomic
  facts extracted from the response vs. the reference — is what's stated actually the
  same set of facts, not just similar-sounding prose). This is the metric closest to
  "would a human grader call this correct," and the one most sensitive to exact
  wording choices in your reference answers.

### Worked example: why Faithfulness and Context Recall can disagree

Say the ground truth for "What's the refund window for annual plans?" is "30 days,
full refund." If your pipeline retrieves an unrelated chunk about monthly plans but
the LLM answers "30 days" anyway (because it pattern-matched from training data or a
different part of its context window), you get: **high Faithfulness** if the model's
claim happens to loosely connect to *something* in the (wrong) retrieved context, but
almost certainly **low Context Recall**, because the actual supporting fact ("30 days,
annual plans") was never retrieved. That combination — answer happens to be right,
faithfulness looks fine, but recall is low — is the single clearest signal in the whole
metric suite that your *retriever*, not your generator, is the thing to fix next. This
is exactly the "identify the weakest metric — that's where you improve next" step in
this week's task: the metric that's low tells you which stage of the pipeline to
target, not just that something's wrong.

## Why it matters in production

- **It's what makes "block merge on regression" possible.** A CI pipeline that runs
  RAGAS on every commit against a fixed 50-sample set and fails the build if
  Faithfulness or Context Recall drops below a threshold turns "did this change make
  retrieval worse" from a question someone has to remember to manually check into an
  automated gate — the actual Month 2 goal this week sets up.
- **Splitting retrieval failure from generation failure changes what you fix.** Without
  per-metric breakdown, "the RAG system gave a wrong answer" could mean six different
  things. With it, a Context Recall regression after a chunking change tells you
  precisely where to look, instead of re-reading generation prompts for a retrieval bug.
- **Reference-free metrics can run on real production traffic**, not just a curated
  eval set, because they don't need a ground-truth answer — Faithfulness and Answer
  Relevancy are the two you can compute continuously in production monitoring, not just
  at CI time.

## Tradeoffs & comparisons

| | LLM-judged (Faithfulness, Answer Relevancy, Context Precision, Context Recall, Answer Correctness's factual half) | Pure embedding-based (Semantic/Answer Similarity) |
|---|---|---|
| Cost | An LLM call (sometimes several, e.g. Faithfulness decomposes into per-statement calls) per sample per metric | One embedding call per sample |
| Determinism | Judge-model variance run to run, even at low temperature | Deterministic given a fixed embedding model |
| Catches | Semantic grounding, relevance, factual overlap — things string-matching can't see | Surface-level "reads similarly to reference" — misses paraphrase-level correctness/incorrectness nuance |
| Latency at 50 samples × 6 metrics | Meaningful — budget for it in CI runtime | Negligible |

**RAGAS vs. classic string-overlap metrics (BLEU/ROUGE):** RAGAS's later versions also
expose `BleuScore`/`RougeScore` as lightweight non-LLM alternatives. They're free and
instant but reward surface wording overlap, not meaning — a correct paraphrase scores
low, a wrong answer using the reference's exact vocabulary scores high. Reasonable as a
cheap smoke-test between full RAGAS runs, not a replacement for the LLM-judged metrics
in an actual quality gate.

**RAGAS vs. manual human review:** human review is the ground truth RAGAS is trying to
approximate cheaply, but doesn't scale to "on every commit." The right pattern is
RAGAS for the automated gate, periodic human spot-checks (especially on the samples
RAGAS scores lowest) to catch cases where the LLM judge itself is systematically wrong.

## Common pitfalls

- **The metric API itself is a moving target — this is not hypothetical, it's this
  week's flagged update.** "Answer Relevancy" has been, across versions: a lowercase
  instance imported from `ragas.metrics` used with the legacy dataset-based
  `evaluate()`; a class called `ResponseRelevancy`; and, in the current v0.4-era
  `ragas.metrics.collections` API, `AnswerRelevancy` again, now scored with an async
  `.ascore(**kwargs)` call instead of `single_turn_ascore(sample)`. Don't trust a
  cached tutorial or your own memory of the API — check the class name and call
  signature against your actually-installed version before wiring up a project (see
  this project's `app/metrics.py` for a try/except import fallback that handles this
  directly instead of hardcoding one API shape).
- **Context Precision's reference vs. reference-free variant is easy to run
  accidentally with the wrong one.** Same metric name, but which columns it needs
  (`reference` vs. `response`) depends on which constructor/variant you instantiate —
  passing a dataset missing `reference` to the reference-based variant fails loudly,
  but passing a dataset *with* `reference` to the reference-free variant just silently
  ignores it, which can mask a bug in your dataset-building code.
- **High Faithfulness does not mean the answer is correct** — see the worked example
  above. Faithfulness only checks response-vs-context agreement; a wrong answer that's
  internally consistent with wrong retrieved context still scores faithful. Never
  report Faithfulness alone as "the accuracy metric."
- **LLM-judge non-determinism on a 50-sample set is large enough to matter.** Re-running
  the identical dataset through the identical metrics can shift the aggregate score by
  a few points from judge-call variance alone. Don't treat a single run's number as
  exact; either fix the judge LLM's temperature to 0, run multiple times and report a
  range, or only act on differences larger than your observed run-to-run noise.
- **Synthetic QA pairs generated by the same model family that answers them can be
  trivially easy.** If GPT-4o both writes a question from a passage *and* later
  generates the pipeline's answer, it can end up "recognizing" its own phrasing rather
  than the pipeline genuinely retrieving and reasoning — this is why this week's task
  keeps 10 hand-labeled samples in the mix as a harder, non-self-generated anchor.
- **Averaging 6 metrics over only 50 samples is noisy.** A couple of pathological
  samples (a malformed retrieval, an empty context) can swing an aggregate metric
  meaningfully. Always inspect the lowest-scoring individual samples, not just the
  mean, before concluding a pipeline component regressed.

## Check yourself

1. A pipeline's Faithfulness score is 0.95 but Context Recall is 0.40. What does that
   combination suggest is broken, and which pipeline stage would you investigate first?
2. Explain why Answer Relevancy needs no `reference`/ground-truth answer, but Context
   Recall does. What would happen if you tried to compute Context Recall on live
   production traffic with no ground truth available?
3. Your CI pipeline pins RAGAS to a specific version and imports
   `ragas.metrics.collections.AnswerRelevancy`. A teammate upgrades RAGAS in a
   dependency bump PR and the import breaks. Why did this happen, and what would you
   put in place so a RAGAS version bump fails loudly in CI rather than silently
   changing which metrics run?
4. You generate 40 of your 50 evaluation samples synthetically with GPT-4o from the
   same corpus your pipeline retrieves from. What's the risk in trusting this set
   alone as a regression gate, and how does keeping 10 hand-labeled samples mitigate it?
5. Between Faithfulness, Answer Relevancy, Context Precision, Context Recall, Answer/
   Semantic Similarity, and Answer Correctness — which are reference-free and which
   are reference-based? For each reference-based one, name the specific piece of
   information it needs that a reference-free metric doesn't.
