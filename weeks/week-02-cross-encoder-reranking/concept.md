# Week 2 — Cross-Encoder Reranking (Two-Stage Retrieval)

## Overview

Week 1 built a hybrid retriever: dense (pgvector) and sparse (BM25/pg_search)
candidates fused with Reciprocal Rank Fusion into one ranked list. That
retriever is a **bi-encoder** architecture — the query and every document
are embedded *independently*, so "relevance" is reduced to a cheap vector
comparison (cosine distance, BM25 score) computed without the model ever
seeing the query and a candidate document side by side. That's exactly what
makes it fast enough to search a whole corpus, and exactly what caps its
precision: it can rank 50,000 documents in milliseconds, but it can't reason
about the specific interaction between *this* query and *this* document.

A **cross-encoder** does the opposite trade: it takes `(query, document)`
as one joint input and outputs a single relevance score, with full
attention between every query token and every document token. That's far
more accurate — it's the closest thing to "actually reading both and
judging" a model can do — but it's also O(n) full forward passes for n
candidates, so it's too slow to run over an entire corpus. The standard fix
is **two-stage retrieval**: a fast bi-encoder (or hybrid retriever) narrows
millions of documents down to a small pool (10s), then a cross-encoder
reranks just that pool with the accuracy budget it needs. This week adds
that second stage on top of Week 1's hybrid pipeline and measures what it
actually buys you.

## Core concept, in depth

### Why a second stage, mechanically

A bi-encoder computes `embed(query)` and `embed(doc)` once each, then
compares them with a fixed function (cosine similarity, BM25 score). The
model that produced `embed(doc)` never saw the query at encoding time — it
had to compress "everything this document could ever be relevant to" into
one fixed-size vector, ahead of time, for every document in the corpus.
That's an approximation by construction: negation, quantities, entity
disambiguation, and multi-hop conditions frequently get lost in that
compression, because a single dense vector has to represent the document
against *every possible future query* at once.

A cross-encoder never precomputes anything per-document. Given `(query,
doc)`, it runs both through the same transformer with cross-attention
between them — e.g. `[CLS] query [SEP] document [SEP]` through a BERT-style
encoder, with a classification head on `[CLS]` producing one relevance
logit. The model can attend from any query token to any document token and
back, so it can actually check "does this document's SKU number match the
SKU number in the query" the way a bi-encoder's fixed embedding never
could. The cost is that this has to be redone from scratch for every
`(query, doc)` pair — there's no reusable per-document vector to precompute
and index. That's why it only runs over Stage 1's output pool, never the
whole corpus.

### The pipeline built this week

```
query
  |
  v
Stage 1 (bi-encoder / hybrid, Week 1's retriever, unchanged)
  dense (pgvector HNSW) + sparse (pg_search BM25) -> RRF fusion
  -> top 25 candidates (RERANK_POOL_SIZE, app/config.py)
  |
  v
Stage 2 (cross-encoder rerank, new this week)
  every (query, candidate) pair scored jointly
  -> reordered, truncated to top 10 (FINAL_TOP_K)
```

`app/retriever.py`'s `hybrid_candidates()` is exactly Week 1's
`HybridRRFRetriever`, just returning 25 candidates instead of a final 10 —
Stage 2 needs room to reorder *within* the pool, so the pool has to stay
wider than the final result list, or there's nothing left for reranking to
do. `app/rerankers.py` implements Stage 2 twice, behind the same
`rerank(query, candidates, top_n)` interface:

- **`CohereReranker`** — calls the managed Cohere Rerank API
  (`client.rerank(model="rerank-v3.5", query=..., documents=[...],
  top_n=...)`). No model to host; you pay per query, cost and latency are
  Cohere's infrastructure's problem, not yours.
- **`BGEReranker`** — loads `BAAI/bge-reranker-base` locally via
  `sentence_transformers.CrossEncoder` and calls `.predict([[query, doc],
  ...])`. No API key, no per-query cost, no data leaving your machine — but
  you own the compute, the model version, and the ops.

### Where this fits into LlamaIndex's abstraction (and why this project skips it)

`app/retriever.py` already leans on `llama-index-core` for Stage 1
(`BaseRetriever`, `NodeWithScore`, `QueryBundle`, `TextNode`, carried over
from Week 1). LlamaIndex also has a built-in shape for Stage 2: a
**`BaseNodePostprocessor`** that runs after a retriever, in a pipeline —
`retriever.retrieve(query) -> postprocessor.postprocess_nodes(nodes,
query_bundle) -> ...`. The two rerankers built by hand here map directly
onto concrete postprocessors that ship for exactly this purpose:

| This project | LlamaIndex equivalent |
|---|---|
| `BGEReranker` | `SentenceTransformerRerank` (`llama_index.core.postprocessor`) — wraps a `sentence-transformers` `CrossEncoder` the same way |
| `CohereReranker` | `CohereRerank` (`llama_index.postprocessor.cohere_rerank` — a *separate* pip package, not installed here) |

`rerankers.py` reimplements both from scratch behind a minimal
`rerank(query, candidates, top_n)` protocol instead of subclassing
`BaseNodePostprocessor`, for three reasons: the Cohere postprocessor's
package was never added as a dependency; the point of this week is to see
the actual mechanics (pool in, `(query, doc)` pairs scored, reordered
top-N out) without a framework's node/postprocessor object model between
you and it; and `benchmark.py` needs raw `(doc_id, score)` pairs to score
against ground-truth IDs, which the hand-rolled `RerankResult` gives
directly. Worth knowing the mapping exists — in a LlamaIndex-based
production pipeline, this is the interface you'd implement against instead
of hand-rolling `rerankers.py`.

### Worked example, from this week's actual benchmark run

Query: `"app won't start after reboot"` (targets doc
`desktop-client-boot-failure`, a *semantic/paraphrase* match — no literal
token overlap with the query, so BM25 contributes nothing and dense
similarity alone has to carry it).

- **Stage 1 (hybrid RRF) result**: the target document did **not** land in
  the top 10 of the 25-candidate pool at all → recall@10 = 0, NDCG@10 = 0.
  Vocabulary mismatch plus a crowded pool of same-topic distractors pushed
  it out.
- **Stage 2 (BGE cross-encoder) result, reranking that same 25-candidate
  pool**: the target document moved to **rank 3** → recall@10 = 1, NDCG@10
  = 1/log2(4) ≈ **0.5**.

Nothing about the candidate *set* changed — the relevant document was
already sitting somewhere in Stage 1's 25-candidate pool the whole time.
Only the cross-encoder's joint scoring found it and moved it up. This is
the two-stage architecture's entire value proposition in one query: Stage 1
guarantees the answer is *somewhere in the pool* (recall), Stage 2 finds it
*inside* the pool (precision/ranking).

### Why NDCG@10 and not just recall@10

Week 1's benchmark already hit **100% recall@10 on 24 of this week's 25
queries** — hybrid retrieval was already "good enough" to get the right
document into the top 10 almost every time. Recall@10 is binary (hit/miss
within the top k), so it's blind to *where* inside the top 10 the answer
landed — rank 1 and rank 10 score identically. Reranking's real job is
mostly moving an already-present answer from rank 6 to rank 1, which
recall@10 can't see at all. **NDCG@10** (`app/metrics.py`) fixes that: each
rank contributes `1/log2(rank+1)` to the score, so rank 1 scores 1.0, rank
3 scores ≈0.5, rank 9 scores ≈0.29 — reranking's benefit shows up as a
*graded* improvement even when recall@10 was already saturated. See
`app/metrics.py`'s docstring for the exact formula and `test_metrics.py`
for the worked example above as a unit test.

## Why it matters in production

Two-stage retrieval is the default architecture for any RAG or search
system built past a toy prototype — every major vector DB vendor's docs
(Pinecone, Weaviate, Qdrant) and every commercial search engine recommend
it once precision at the top of the ranking starts to matter more than raw
recall. Concretely:

- **Recall alone is not the product.** An LLM given the top 10 retrieved
  chunks doesn't read them uniformly — recency/position bias means chunks
  near the top of the context window get weighted more heavily by the
  model. If the actually-relevant chunk is buried at rank 9 instead of rank
  1, RAG answer quality degrades even though "the right chunk was
  technically retrieved."
- **Reranking is cheap exactly because it's Stage 2.** Running
  `bge-reranker-base` (a ~278M-parameter cross-encoder) over 25 candidates
  costs ~166ms on CPU in this week's benchmark (measured below). Running it
  over the full corpus instead — the mistake reranking exists to avoid —
  would scale linearly with corpus size and make this architecture
  unusable past a few hundred documents.
- **Managed vs. self-hosted is a real infrastructure decision, not a detail.**
  Cohere Rerank means no GPU/CPU capacity planning, no model-version drift
  to manage, but a per-query cost, a network round trip, and your query and
  document text leaving your infrastructure — a real constraint for
  regulated or on-prem data. BGE means the opposite trade on every axis.
  This is precisely why the task has you A/B both rather than picking one
  by reputation.

## Tradeoffs & comparisons

| | Bi-encoder (Stage 1, Week 1) | Cross-encoder (Stage 2, this week) |
|---|---|---|
| Input to the model | Query and doc embedded separately | Query + doc, jointly, with cross-attention |
| Precision | Lower — fixed vector has to generalize to any future query | Higher — sees this exact query/doc pair |
| Cost per candidate | Amortized: doc embeddings precomputed once, indexed | Full forward pass per (query, doc) pair, every query |
| Scales to | Whole corpus (millions of docs, via HNSW/BM25 index) | Only a small pool (10s–100s of candidates) |
| Can be precomputed/indexed | Yes (this is *why* it scales) | No — depends on the query, computed at query time |

| | Cohere Rerank (managed) | BGE Reranker (self-hosted) |
|---|---|---|
| Setup | API key, zero infra | Model download + local compute |
| Cost model | Per query/search-unit, pay-as-you-go | Fixed (your compute), no per-query fee |
| Latency | Network round trip + Cohere's inference time | Local inference only, no network hop |
| Data residency | Query + doc text sent to Cohere | Never leaves your machine |
| Model control | Cohere controls versioning/updates | You control the exact checkpoint, can fine-tune |
| Measured this week | *(needs `COHERE_API_KEY` — see README)* | NDCG@10 0.910 → 0.945, +166.2ms/query (see below) |

## Common pitfalls

- **Reranking over too small a pool.** If Stage 1's pool ≤ Stage 2's final
  `top_n`, there's nothing for the cross-encoder to reorder *into* — the
  relevant document either made the pool or it didn't, and reranking can't
  invent recall Stage 1 never gave it. `RERANK_POOL_SIZE` (25) must stay
  larger than `FINAL_TOP_K` (10) — see `app/config.py`.
- **Judging reranking by recall@10 alone.** As shown above, recall@10 can
  legitimately show *no* change while reranking is doing real, measurable
  work — check NDCG@10 (or MRR), not just hit/miss.
- **Reranking is not strictly monotonic per query.** This week's own run
  found one query (`BATCHJOB90441`, an exact-token match) where BGE
  reranking *dropped* NDCG@10 from 1.0 to 0.63 — the cross-encoder moved
  the correct document from rank 1 to rank 3. A model trained mostly on
  natural-language relevance judgments doesn't automatically defer to exact
  token matches the way BM25 does. **Average lift across a benchmark
  hiding per-query regressions is a real production risk** — always look
  at the per-query table, not just the mean (see `app/benchmark.py`'s
  output).
- **Treating "managed API available" as "no failure mode to handle."**
  `CohereReranker` raises `RerankerUnavailable` if `COHERE_API_KEY` isn't
  set; `app/benchmark.py` catches that once and skips the column with a
  printed note instead of crashing the whole run. A production system needs
  the same fallback (e.g. serve Stage 1's order un-reranked) for API
  outages/rate limits, not just for local dev.
- **Not accounting for reranker latency in the calling budget.** +166ms per
  query is real, added serially to whatever Stage 1 already cost — for a
  latency-sensitive endpoint this has to be budgeted for explicitly, not
  discovered in production.

## Check yourself

1. Why can a cross-encoder's document representation not be precomputed and
   indexed the way a bi-encoder's can? What does that cost you, and what
   does it buy you?
2. In this week's worked example, Stage 1's hybrid RRF completely missed
   the relevant document (NDCG@10 = 0) and Stage 2 recovered it to rank 3.
   Could Stage 2 have recovered a document that never appeared in Stage 1's
   25-candidate pool at all? Why or why not — and what does that imply
   about `RERANK_POOL_SIZE`?
3. Recall@10 was already 96% before reranking, yet NDCG@10 still improved
   measurably. Explain, in terms of the NDCG formula, how both of those can
   be true at once.
4. Give one concrete production scenario where you'd pick Cohere Rerank
   over BGE, and one where you'd pick BGE over Cohere. What's the deciding
   factor in each?
5. This week's benchmark found one query where reranking made the ranking
   *worse*. What does that tell you about deploying a reranker based on a
   single aggregate metric, and what would you check before shipping it?
