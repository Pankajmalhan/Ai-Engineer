# Week 1 — Hybrid Search Architecture (BM25 + Dense + RRF)

## Overview

"Retrieval" in RAG usually gets reduced to "embed the query, cosine-search a vector
index, take the top k." That works until it doesn't — and it stops working in very
predictable ways. Dense embeddings are excellent at *semantic* similarity (they know
"car" and "automobile" are close) but they are surprisingly bad at *exact* matches:
product SKUs, error codes, function names, acronyms, people's names, anything where the
literal token matters more than the "meaning." Sparse lexical retrieval (BM25) is the
mirror image — it's exact-match-only and knows nothing about synonyms or paraphrase.

Hybrid search is the architecture that runs both retrieval strategies over the same
corpus, gets two independently-ranked lists of candidates, and fuses them into one
ranking that inherits the strengths of each. This week is about understanding *why*
each half fails on its own, and building the standard production pattern for combining
them: pgvector for dense, `pg_search` (BM25, via ParadeDB) for sparse, Reciprocal Rank
Fusion (RRF) to merge.

## Core concept, in depth

### Why single-vector (dense-only) retrieval fails

A dense retriever embeds text into a fixed-size vector using a model trained to place
semantically similar text nearby in vector space. This is learned similarity — it is
*not* memorized vocabulary. Two failure modes follow directly from that:

**1. Vocabulary mismatch (the "it's too smart" failure).** Embedding models compress
meaning, and compression is lossy. A model trained mostly on natural prose will
generally place `"ERR_CONN_TIMEOUT_502"` and `"ERR_CONN_RESET_503"` near *each other*
in vector space (they look like the same "kind" of token — an error code — even though
they mean different things), while a user query containing the literal string
`ERR_CONN_TIMEOUT_502` may not score highest against the document that literally
contains that string. The model has no privileged notion of "this exact substring
matters"; it just sees tokens and produces a fuzzy semantic fingerprint.

**2. The exact-match gap.** Rare, out-of-vocabulary, or high-specificity tokens — part
numbers, legal citation IDs, usernames, exact function signatures — are exactly the
tokens dense models are worst at representing distinctly, because they're rare in the
model's training distribution and get squashed toward generic embeddings. Yet these are
often precisely the tokens a user copy-pastes into a search box because they already
know the exact term they want. A user who searches `"psycopg2.OperationalError"`
wants documents containing that literal string — dense retrieval may hand back
generically-related database-error documents instead, ranked by "vibes."

Both failures share a root cause: dense retrieval has no mechanism that rewards a exact
token match more than a semantically-similar-but-different one. It optimizes for the
wrong invariant when the user's query *is* the discriminating signal.

### Why sparse-only (BM25) retrieval fails

BM25 is the mirror-image tool. It scores a document for a query based on term
frequency (how often each query term appears in the document) and inverse document
frequency (how rare that term is across the whole corpus), with length normalization so
long documents don't win purely by containing more words. Concretely, for a query with
terms `q1...qn`:

```
score(D, Q) = Σ IDF(qi) · ( f(qi, D) · (k1 + 1) ) / ( f(qi, D) + k1 · (1 - b + b · |D|/avgdl) )
```

where `f(qi, D)` is term frequency in document `D`, `|D|` is document length, `avgdl` is
average document length across the corpus, and `k1`, `b` are tuning constants
(saturation of term-frequency reward, and how strongly length is penalized).

BM25 is precise but *brittle to phrasing*: it has zero concept of synonymy. A query for
`"how do I terminate a process"` will not match a document that only ever says `"kill a
running task"` — there's no shared token, so the score is zero, regardless of how
obviously related the two phrases are to a human reader. This is the flip side of the
vocabulary-mismatch problem: BM25 fails on paraphrase, dense fails on precision.

### The fix: run both, fuse the rankings

Hybrid search doesn't try to build one model that's good at both — it keeps two
independent, specialized retrievers and combines their *rankings* after the fact. This
week's target architecture, mapped onto Postgres:

```
                     ┌───────────────┐
   query ──────────► │  embed query  │──────► pgvector ANN search ──► dense ranked list
        │            └───────────────┘                                     │
        │                                                                  ▼
        │            ┌───────────────┐                              ┌───────────┐
        └──────────► │  BM25 tokens  │──────► pg_search BM25 index ─►│    RRF    │──► final ranking
                     └───────────────┘        (sparse ranked list)   └───────────┘
```

Both retrievers run against the *same* corpus, stored in the *same* table — one column
holds a dense embedding (`vector` type, via `pgvector`), another is covered by a BM25
index (via `pg_search`, ParadeDB's Postgres extension, using its `@@@` match operator
and `paradedb.score()`). Each retriever returns its own top-N candidates with its own
scores. Critically, those scores are **not comparable** — a cosine similarity of 0.82
and a BM25 score of 14.3 live on different scales and can't be added together
meaningfully. This is exactly the problem RRF exists to solve.

### Reciprocal Rank Fusion (RRF)

RRF sidesteps the "scores aren't comparable" problem by throwing the raw scores away
and fusing on **rank position** instead. For each document `d` that appears in one or
more of the candidate lists:

```
RRF(d) = Σ_over_lists  1 / (k + rank_list(d))
```

- `rank_list(d)` is `d`'s 1-indexed position in that particular ranked list (dense or
  sparse). A document that doesn't appear in a list contributes 0 for that list.
- `k` is a small constant (60 is the conventional default from the original RRF paper)
  that dampens the influence of very high ranks — without it, the #1 slot would
  dominate disproportionately (`1/1` vs `1/2` is a 2x gap; `1/61` vs `1/62` is a ~1.6%
  gap). Larger `k` flattens the fusion; smaller `k` makes it more winner-take-all.

Worked example — query `"connection timeout error"` against a 3-document toy corpus,
retrieving top-3 from each retriever:

| doc | dense rank | sparse rank | RRF score (k=60) |
|-----|-----------|-------------|-------------------|
| A   | 1         | 3           | 1/61 + 1/63 = 0.0322 |
| B   | 2         | —(not in top-3) | 1/62 + 0 = 0.0161 |
| C   | 3         | 1           | 1/63 + 1/61 = 0.0322 |

Doc A and Doc C tie despite neither being #1 in either individual list — because each
was *strong in one modality and still decent in the other*. That's the entire value
proposition of RRF: it rewards documents that both retrievers agree are relevant, and
it lets a document that's #1 in exactly one list (but absent from the other) get
outranked by a document that placed respectably in *both*. No score normalization,
no learned fusion weights, no training data required — that's why RRF is the default
production choice over something like weighted linear score combination.

### Where this maps to your task this week

- **pgvector column** (`embedding vector(384)` or similar) + `USING hnsw` /
  `USING ivfflat` index → dense candidate list via `ORDER BY embedding <=> query_vec`.
- **pg_search BM25 index** (ParadeDB's `bm25` index type) over a text column → sparse
  candidate list via `WHERE content @@@ query_string ORDER BY paradedb.score(id) DESC`.
- **RRF fusion function** → pure application code (or SQL `WITH` CTEs), merges the two
  ranked ID lists by the formula above, returns one final ranked list.
- **Benchmark** → recall@10 measures, of the documents you *know* are relevant to a
  query, what fraction show up in the top 10 of the ranking. Comparing dense-only vs.
  hybrid recall@10 across 20 queries is what actually proves (or disproves) that fusion
  helped — don't take the architecture's superiority on faith, measure it on your own
  corpus and queries, because whether it helps at all is corpus- and query-dependent.

## Why it matters in production

Almost every production RAG/search system that has moved past a demo runs hybrid
retrieval, because real user queries are a mix of "vague semantic ask" and "I know
exactly what string I'm looking for," often in the *same* query. Support search over
product docs needs to match both `"my app keeps crashing on startup"` (semantic) and
`"Error 0x8007042B"` (exact). Code search needs to match both `"function that retries
failed requests"` (semantic) and `retry_with_backoff` (exact identifier). E-commerce
search needs both `"warm winter jacket"` (semantic) and a literal SKU or brand name
pasted from an email.

At scale, this also becomes a systems/cost problem, not just a quality one: dense ANN
indexes (HNSW/IVFFlat) and BM25 indexes have very different build/maintenance cost
profiles, different index sizes, and different query latencies. Running them in the
same database (Postgres, via pgvector + pg_search) rather than a separate vector DB
plus a separate search engine (e.g. Pinecone + Elasticsearch) is itself a production
decision — it trades some retrieval sophistication (dedicated engines often have more
tuning knobs) for massively simpler operations: one database, one backup story, one
consistency model, one place transactions and joins work normally against your document
metadata.

If you skip hybrid and ship dense-only, the failure is silent — it doesn't error, it
just quietly returns "reasonable-looking" but wrong top results for exact-match queries,
which is a categorically harder class of bug to notice in production than a crash.

## Tradeoffs & comparisons

| | Dense (pgvector) | Sparse/BM25 (pg_search) | Hybrid (RRF-fused) |
|---|---|---|---|
| Synonym/paraphrase queries | Strong | None | Strong (inherits dense) |
| Exact-token / rare-term queries | Weak | Strong | Strong (inherits sparse) |
| New vocabulary the embedding model never saw | Weak | Strong (pure statistics, no training) | Strong |
| Interpretability of "why did this match" | Low (opaque vector) | High (literal term match) | Medium |
| Index build/update cost | Higher (ANN index, needs re-embedding on content change) | Lower (classic inverted index) | Both costs, paid independently |
| Tuning required | Embedding model choice, ANN params | k1/b (usually fine at defaults) | + RRF's k constant |
| Extra infra vs. dense-only | — | + one index type, same DB | + fusion logic (cheap, no training) |

RRF vs. alternative fusion strategies, briefly: **weighted linear combination** of
normalized scores can outperform RRF *if* you have relevance-labeled data to tune the
weights on, but is fragile to distribution shift (a corpus update changes BM25's score
distribution; embedding model changes shift cosine distributions) and needs
re-tuning. **Learned re-ranking** (e.g. a cross-encoder over the fused candidates) is
strictly more accurate but adds real latency and a second model to serve. RRF is the
right default specifically because it's parameter-light, needs no training data, and
is robust to the two input lists being on totally different, non-comparable scales —
which is exactly the situation dense-cosine vs. BM25-score puts you in.

## Common pitfalls

- **Comparing raw scores instead of ranks.** Trying to normalize and add a cosine
  similarity to a BM25 score directly is the mistake RRF exists to avoid — the score
  distributions aren't just on different scales, they have different *shapes* (cosine
  is bounded [-1,1] and BM25 is unbounded and corpus-dependent), so no single
  normalization constant transfers across queries.
- **Fetching too few candidates per list before fusing.** If you only pull the top 10
  from each retriever and fuse, you can miss a document that was, say, rank 15 in dense
  and rank 2 in sparse — it never gets a chance to be considered. Pull a wider
  candidate set (e.g. top 50-100 from each) into the fusion step, then truncate to the
  final top-k *after* RRF.
- **Forgetting length normalization matters for BM25's `b` parameter** when your corpus
  has wildly different document lengths (short FAQ snippets next to long articles) —
  the defaults (`k1=1.2, b=0.75`) are reasonable starting points, not universal truths.
- **Treating recall@10 improvement as guaranteed.** Hybrid helps *when your query mix
  actually contains exact-match-sensitive queries*. If you benchmark with 20 purely
  paraphrase-style queries, dense-only may already win and fusion adds nothing but
  latency — this is why the benchmarking task matters, not just implementing fusion.
- **Not indexing the right column for BM25.** `pg_search`'s BM25 index needs to be
  built over the raw text column with its own index type; it is not the same thing as
  Postgres's built-in `tsvector`/`GIN` full-text search (that's a different, older,
  non-BM25-ranked mechanism) — don't conflate the two when the task says "BM25."

## Check yourself

1. A user searches your docs for `"NullPointerException"` and gets back generically
   related "debugging tips" articles instead of the doc that contains that literal
   string. Which retriever (dense or sparse) is under-performing here, and why?
2. Why can't you just add a normalized BM25 score to a normalized cosine similarity and
   sort by the sum? What specifically goes wrong?
3. In RRF, what does increasing `k` from 60 to 1000 do to the final ranking, and why?
4. You fuse two lists where a document is rank 1 in dense but doesn't appear at all in
   the sparse top-50. What RRF score contribution does it get from the sparse list, and
   why is that different from an implicit rank-of-51?
5. If your recall@10 benchmark shows *no* improvement from hybrid over dense-only on
   your 20 queries, is that necessarily evidence hybrid search doesn't work? What would
   you check before concluding that?
