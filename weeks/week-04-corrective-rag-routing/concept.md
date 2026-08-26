# Week 4 — Query Routing and Corrective RAG

## Overview

Weeks 1-3 built better and better ways to *retrieve*: hybrid BM25+dense search,
cross-encoder reranking, ColBERT late interaction. All of that assumed retrieval was
always the right move, and that whatever came back was good enough to hand to the LLM.
Neither assumption holds in production. Some queries ("hi, how are you?") shouldn't hit
a retriever at all. Some queries need a different retrieval strategy than others (a
question about a code symbol wants token-level matching, not paragraph-level semantic
search). And even the best retriever sometimes returns garbage — the corpus doesn't
cover the question, the query was ambiguous, the index is stale — and a RAG pipeline
that blindly stuffs bad chunks into the prompt just launders bad retrieval into a
confident-sounding wrong answer.

This week closes both gaps with two pieces that compose into one pipeline:

1. **A query router** — classify the query first, dispatch to the retrieval strategy
   that actually fits it (or skip retrieval entirely).
2. **Corrective RAG (CRAG)** — grade what came back before trusting it; if it's weak,
   correct course by escalating to web search instead of answering from bad context.

(A third piece, DSPy — treating the grader's prompt as something optimized against
labeled examples instead of hand-tuned — is part of this week's roadmap but
deliberately **deferred**: it's its own framework worth learning on its own terms
first, rather than bolted onto this project before that groundwork is in place. Revisit
it once you've gone through DSPy's own docs.)

## Core concept, in depth

### 1. Query routing

A router is a classifier that sits in front of your retrieval stack and picks a path:

```
query → router → {FACTUAL → hybrid search (docs), CODE → hybrid search (code, BM25-weighted), CONVERSATIONAL → direct LLM}
```

The reason this beats "always run the full pipeline" is that retrieval needs differ by
query type, even when the underlying retrieval *mechanism* stays the same. This
project's `hybrid_search` — real BM25 (Week 1's sparse leg) fused with real dense
vectors from a pgvector store via reciprocal rank fusion — serves both the FACTUAL and
CODE routes, but against two different pgvector collections, and weighted differently:
FACTUAL retrieval treats BM25 and the dense leg equally, while CODE retrieval weights
BM25 more heavily, because exact identifiers, error strings, and API names
(`getUserById`, `NullPointerException`) matter more as *lexical* matches than semantic
ones — a dense embedder trained on natural-language similarity will happily rank a
prose paragraph about null checks above the exact function that throws the error,
which BM25 won't. And "how's it going" doesn't need retrieval at all — routing it
through either collection wastes latency and risks pulling in irrelevant chunks that
*degrade* the answer versus just answering directly.

A natural question: why not give CODE queries a specialized retrieval *algorithm*
instead of just a differently-weighted collection — e.g. ColBERT/PLAID's token-level
late interaction (Week 3), which is a genuinely better fit for exact-symbol matching
than any BM25+dense hybrid? Because that's a real cost/complexity tradeoff, not a free
upgrade: ColBERT needs its own indexing pipeline, a much larger per-token index (one
vector per token instead of one per chunk), and a separate serving stack from whatever
already runs your Postgres-backed retrieval. For a router with only two
retrieval-needing branches, standing up a second retrieval *system* just for the CODE
route is a lot of infrastructure to buy back a smaller, harder-to-quantify accuracy
gain than the BM25-weighting already captures cheaply. ColBERT earns its complexity
when token-level precision is the primary retrieval workload (e.g. a codebase-only
search product), not as one branch of a three-way router.

**How routing is actually implemented.** There are two common approaches, and this
week's project uses a blend:

- *Semantic routing*: embed the query, embed a handful of representative example
  queries per class, classify by nearest-centroid or max cosine similarity. No LLM
  call, sub-millisecond, deterministic given the embedding model. This is what
  libraries like `semantic-router` do, and it's what LangChain's `RunnableBranch` /
  custom router chains wrap when you back them with embeddings instead of an LLM call.
- *LLM routing*: ask the LLM "which category is this query?" with structured output.
  More flexible (handles novel phrasings, can explain its reasoning) but adds latency
  and a network call to every single query — expensive when routing is on the hot path.

The project's `SemanticRouter` uses TF-IDF-similarity-to-prototypes as the primary
signal (fast, offline, no API key needed on the hot path — the "no embedding model"
cousin of true semantic routing, trading some accuracy on paraphrases for zero
infrastructure) plus a few cheap structural heuristics for the CODE class (presence of
code fences, `snake_case`/`camelCase` identifier density, error-message punctuation)
as a second signal, because pure word-overlap similarity under-separates "how do I fix
this stack trace" from "explain stack traces conceptually" — surface features help
exactly there. This mirrors how production routers are rarely *one* signal; they're a
small ensemble with a confidence score.

**Escalating instead of guessing: `CascadingRouter`.** `SemanticRouter` on its own
just defaults to FACTUAL whenever its confidence is too low — safe, but it means every
genuinely ambiguous query silently gets whatever the safe default happens to be,
right or wrong, with no way to do better without also making *every* query pay for a
smarter (and slower, costlier) classifier. `CascadingRouter` wraps `SemanticRouter`
with a second tier instead: only the low-confidence minority gets escalated to
`LLMRouteClassifier`, a real LLM call. In practice, most real traffic isn't actually
ambiguous — if TF-IDF confidently resolves 90-95% of queries for free, an LLM call is
only ever paid on the hard 5-10%, which is a large cost reduction for accuracy that's
concentrated exactly where the cheap tier was weakest, rather than spread thin across
every request.

The other half of `CascadingRouter` is a feedback loop, not just a fallback: every
escalation gets appended to a JSONL log (query, what Tier 1's per-class scores were,
what the LLM decided). The intended workflow is to periodically review that log and
fold well-understood queries back into `PROTOTYPES` — this project's seed set already
grew this way once, from 8 hand-written examples/class to ~25, specifically to shrink
how often real queries need to reach Tier 2 at all. `escalation_rate` (the fraction of
routed queries that hit Tier 2) is the metric this loop is trying to drive down over
time — a router that starts at 20% escalation and settles to 5% after a few rounds of
folding logged queries back into `PROTOTYPES` is the loop actually working.

### 2. Corrective RAG (CRAG)

CRAG (Yan et al., 2024) adds a checkpoint *after* retrieval and *before* generation:

```
retrieve → grade each chunk → decide {Correct, Incorrect, Ambiguous} → act → generate
```

**Grading.** Each retrieved chunk gets a relevance score against the query, typically
from a lightweight LLM-as-judge call: "on a scale of 0 to 1, how relevant is this chunk
to answering this query?" This is a narrower, cheaper LLM call than generation itself —
it doesn't need to reason about the answer, just judge relevance, so a small/fast model
is usually enough.

**Deciding and acting.** The paper uses two thresholds on the *best* retrieved chunk's
score, and this project's `CorrectiveRAG` implements that directly rather than a
single mean-based simplification:

- `max(chunk scores) > 0.7` → **Correct**: keep retrieval, but still run it through
  knowledge refinement (below) rather than trusting the whole chunk verbatim.
- `max(chunk scores) < 0.3` → **Incorrect**: discard retrieval entirely, rewrite the
  query into something search-engine-shaped (`rewrite_query`: "Why does getUserById()
  throw a NullPointerException?" → "getUserById NullPointerException"), and answer
  from web search results instead.
- otherwise → **Ambiguous**: do both — refine the retrieved chunks *and* run the
  (rewritten) web search, and recompose both into one context.

Max, not mean, is the right statistic here: mean relevance across all retrieved chunks
can mask one genuinely great chunk buried among several irrelevant ones (see Check
Yourself Q1) — max asks "did retrieval find *anything* good," which is the actual
question CRAG needs answered before it decides whether to trust retrieval at all.

**Knowledge refinement.** Whichever context ends up selected — refined retrieval, web
results, or both — gets passed through a refiner before generation: split into
sentences, score each by relevance to the query, keep only the ones that clear a bar,
discard the rest. This is the paper's "decompose-then-recompose": a chunk that's 80%
irrelevant filler around one useful sentence should contribute one bullet, not the
whole chunk. The offline `HeuristicRefiner` does this by keyword overlap (and — the
first version of this pipeline missed this — needs to actually *drop* zero-relevance
sentences rather than padding a fixed bullet count with them, or it just re-introduces
the noise it's supposed to remove); the `LLMRefiner` does the same job with an LLM
call, closer to what the paper's decompose-then-recompose actually does.

**Generation.** The refined bullets are the final context handed to a generator, which
answers strictly from that context (and says so plainly if the context doesn't cover
the question, rather than guessing). The offline `ExtractiveAnswerer` doesn't
generate anything — it formats the bullets and labels itself as non-generative, so it's
never mistaken for a real answer; `LLMAnswerer` is the real generation step.

**What's still a deliberate simplification, and where.** The *architecture* now
matches the paper — dual threshold, refine, rewrite, generate. What's still
simplified is which *implementation* runs by default: every one of grade / refine /
rewrite / answer has a free, deterministic, offline heuristic version and a real
LLM-backed version behind the same interface (a `Protocol` per step, all four
LLM-backed versions are plain hand-written prompts via Instructor + Anthropic), and
the heuristics are cruder than an LLM at all four jobs — see the grader comparison
below, which applies identically to the refiner, rewriter, and answerer.

**Why grade instead of just trusting top-k?** Retrieval failures are *silent*. A vector
search always returns its top-k nearest neighbors — even if the nearest neighbor is
still irrelevant, you get an answer back, no error, no signal. Without a grading step,
a RAG system has no way to distinguish "I found the answer" from "I found the least-bad
thing in an index that doesn't cover this." Grading turns that silent failure into a
measurable signal you can branch on.

## Why it matters in production

- **Routing** cuts cost and latency: not every query needs your most expensive
  retrieval path. A support bot answering "thanks!" 30% of the time is burning a full
  hybrid-search-plus-rerank pipeline on messages that need zero retrieval, at scale
  that's real infra spend for zero quality benefit. The same reasoning applies one
  level up, inside the router itself: `CascadingRouter` only pays for an LLM call on
  the confidence-flagged minority of queries, not on every single one.
- **CRAG** is a direct hedge against hallucination-from-bad-context, which is the
  single most common RAG failure mode in the field: the retriever returns *something*,
  the LLM dutifully "answers" from it, and the answer is confidently wrong because the
  context never actually addressed the question. Systems serving domains where wrong
  answers are costly (support, legal, medical, internal tooling with irreversible
  actions) need this checkpoint, not just "trust the top-k."

## Tradeoffs & comparisons

| | Router-first RAG | Always-full-pipeline |
|---|---|---|
| Latency on trivial queries | Low (skip retrieval) | High (always retrieves) |
| Correctness on specialized queries | High (code → BM25-weighted collection) | Medium (one-size-fits-all) |
| Failure mode | Misrouted query gets wrong strategy | Consistently mediocre everywhere |

**BM25-weighted hybrid vs. ColBERT for the CODE route**: a heavier-BM25 hybrid search
over a pgvector collection is cheap to run (one retrieval stack, one index type,
reuses the same Postgres instance as FACTUAL) but still loses to genuine token-level
late interaction on precision — it can't tell "the query token `getUserById` best
matches this exact substring" the way ColBERT's per-token MaxSim can, it can only
weight whole-chunk lexical overlap more heavily. ColBERT wins decisively once code/API
search *is* the product, not one branch of three; until then, the operational cost of
running two full retrieval stacks usually isn't worth what it buys.

| | CRAG (grade + fallback) | Plain RAG (trust top-k) |
|---|---|---|
| Handles corpus gaps | Yes — escalates to web search | No — answers from irrelevant chunks |
| Latency/cost | Higher (grading call + possible web call) | Lower |
| Failure mode | Miscalibrated grader over/under-triggers fallback | Silent hallucination on corpus gaps |

**Heuristic grader vs. LLM-as-judge grader**: a heuristic (embedding/lexical overlap)
grader is free and instant but blind to semantic relevance that doesn't share surface
form ("revenue" query, "top-line income" chunk — an embedding grader partially catches
this, a keyword-overlap grader misses it entirely). An LLM-as-judge grader is much
better at true semantic and pragmatic relevance judgments but costs a network call per
chunk and — like any LLM judge — has calibration drift and prompt sensitivity, which is
exactly the kind of thing a framework like DSPy exists to reduce by compiling the
prompt against labeled examples instead of hand-tuning it (see the "DSPy" note in the
Overview — not yet wired into this project).

## Common pitfalls

- **Trusting a single high score under max-based thresholding.** Deciding Correct/
  Incorrect off the *best* chunk's score (as the paper, and this project, actually do)
  means one noisy high score from an otherwise-bad retrieval can swing the whole
  decision to Correct. LLM relevance scores are noisy — the same (query, chunk) pair
  can get different scores across calls — so don't treat a lone 0.72 as trustworthy on
  its own; a production system typically wants either margin around the threshold or a
  "k of n chunks must clear a bar" rule, not "the single highest score decides."
- **Picking the two thresholds once and never revisiting them.** 0.7/0.3 are starting
  points, not laws. They need to be validated against a labeled set of "should this
  have been Correct/Incorrect/Ambiguous" examples, the same way you'd validate any
  classifier's decision boundary -- and the gap between them (how much of your traffic
  lands in Ambiguous, paying for both retrieval and web search) is itself a tuning
  knob worth watching.
- **Routing with no fallback for low-confidence classifications.** If the router isn't
  confident which class a query belongs to, don't force a pick — route low-confidence
  queries to the safest general-purpose strategy (hybrid search) rather than guessing.
- **Burning web search budget on every ambiguous case.** CRAG's fallback isn't free —
  Tavily calls cost money and add latency. A system that mis-grades frequently and
  escalates too often quietly turns into "always do two retrievals," defeating the
  point of having a fast primary retriever at all.

## Check yourself

1. Give a concrete (query, chunks, scores) example where a mean-relevance-across-
   chunks threshold and the paper's dual-threshold-on-max-score design (what this
   project actually implements) would disagree on Correct vs. Incorrect. Which one is
   right for that example, and why?
2. A query router misclassifies a code question as CONVERSATIONAL and answers directly
   with no retrieval. What's the actual harm, and how would you catch it happening at
   scale (not just in this one example)?
3. Why is grading each chunk with a *cheap* model usually fine even though generation
   needs a stronger one? What would go wrong if the grader model were *weaker* than
   "cheap" — e.g., systematically biased toward high or low scores?
4. Your CRAG pipeline's fallback rate (fraction of queries hitting web search) jumps
   from 5% to 40% overnight with no corpus change. List two possible causes and how
   you'd tell them apart.
5. `CascadingRouter`'s `escalation_rate` starts at 20% and, after several rounds of
   reviewing `router_escalations.jsonl` and folding queries into `PROTOTYPES`, settles
   at a flat 6% and stops dropping further no matter how many more logged queries you
   add. What would you check before concluding "6% is just the irreducible floor for
   this router"?
