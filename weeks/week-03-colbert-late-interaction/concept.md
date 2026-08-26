# Week 3 — ColBERT & Late-Interaction (Multi-Vector) Retrieval

## Overview

Weeks 1 and 2 built the two extremes of the retrieval spectrum. Week 1's
bi-encoder collapses every document into **one vector**, precomputed once
and compared to the query with a cheap dot product — fast enough for a
whole corpus, but that single vector has to represent "everything this
document could ever be relevant to" ahead of time, so fine-grained detail
gets lost in the pooling. Week 2's cross-encoder goes the other way: it
looks at `(query, document)` jointly, with full attention between every
token pair, so it never loses that detail — but nothing about a document
can be precomputed, so it only ever runs over a small pool a cheaper stage
already narrowed down.

**ColBERT** (Khattab & Zaharia, 2020) is the model that asks: what if a
document didn't get pooled into one vector at all? Keep **one embedding per
token** instead, for both the query and every document, and compare a query
to a document by letting every query token independently find its best
match among the document's token embeddings, then sum those best-matches
up. This is **late interaction**: query and document are still encoded
completely independently (no cross-attention, so document token vectors
*can* be precomputed and indexed, exactly like a bi-encoder) — but the
comparison that follows operates at token granularity instead of collapsing
to a single number, closing most of the accuracy gap to a cross-encoder
without paying its per-query cost.

## Core concept, in depth

### From pooled vectors to MaxSim

Both a bi-encoder and ColBERT start the same way: run the query and the
document through a BERT-style encoder, which produces one contextualized
vector *per token*. A bi-encoder throws almost all of that away — it pools
every token vector into a single vector (mean pooling, or the `[CLS]`
vector) and keeps only that. ColBERT keeps every token vector (each
projected down from BERT's 768 dimensions to a much smaller 128 via one
extra linear layer, to keep the index affordable), and defines relevance as
**MaxSim**:

```
S(q, d) = Σ_{i in query tokens}  max_{j in doc tokens}  (q_i · d_j)
```

Read left to right: for *each* query token, scan every token embedding in
the document and take the single highest similarity score anywhere in that
document — then add those per-token best-matches up across the whole query.
Every query token gets to independently "shop" the entire document for its
own best match; nothing forces the whole query into one blended
representation the way pooling does.

### Worked example

Query: `"who founded Studio Ghibli"` → 4 query token embeddings after
tokenization, call them `q_who`, `q_founded`, `q_studio`, `q_ghibli`.

Candidate document A (the correct one): *"Hayao Miyazaki and Isao Takahata
founded Studio Ghibli in 1985 after the success of Nausicaä."* Candidate
document B (a same-topic distractor): *"Studio Ghibli's films are
distributed internationally by different partners depending on the
region."*

For query token `q_founded`, MaxSim scans **every** token embedding in the
candidate document and keeps the single best one:

| doc | best-matching doc token for `q_founded` | similarity |
|---|---|---|
| A | `founded` (literal, contextualized near "Miyazaki"/"Takahata") | 0.91 |
| B | `distributed` (same rough "verb about the studio" role, weak match) | 0.38 |

Repeat that lookup independently for `q_who`, `q_studio`, `q_ghibli` against
each document, then sum the four best-matches per document. Document A
racks up a high best-match on *every* query token (`who`→"Miyazaki",
`founded`→"founded", `studio`→"Studio", `ghibli`→"Ghibli"), so its MaxSim
sum is high. Document B only really satisfies `studio` and `ghibli` well —
`who` and `founded` have nothing good to latch onto anywhere in that
sentence, so those two terms contribute weak scores and drag document B's
sum down, even though at the topic level ("this is about Studio Ghibli")
the two documents look similar. That per-token independence — rather than
one blended "topic vector" — is exactly what a single pooled embedding
cannot do: a bi-encoder's one vector for document B would still land fairly
close to the query's one vector, because most of the sentence *is* about
the right topic; MaxSim instead penalizes it token-by-token for the terms
it never actually satisfies.

This is also why **raw MaxSim scores and cosine similarity aren't
comparable by magnitude** — a task called out explicitly in this week's
plan. Cosine similarity is one number in `[-1, 1]`. MaxSim is a **sum
across every query token**, so a 4-token query and a 12-token query produce
scores on entirely different scales even for equally good matches — you
compare MaxSim scores to each other (for ranking, same query), never to a
cosine value, and never across queries of different lengths without
normalizing first.

### Query augmentation: `[Q]`/`[D]` markers and `[MASK]` padding

Two mechanics from the original paper, both preserved in the model
checkpoint (`colbert-ir/colbertv2.0`) this week's project loads:

- Every query is prefixed with a `[Q]` marker token, every document with
  `[D]` — same shared encoder weights, but the marker tells the model which
  role it's encoding in, since query text and document text get treated
  differently downstream (queries are padded, documents aren't).
- Queries are then padded with `[MASK]` tokens up to a fixed length (32 in
  the original paper). Because the model was *trained* with this padding,
  it learns to use those extra mask positions as soft, contextually-filled
  "query expansion" terms — attention lets a mask position pick up meaning
  related to the real query tokens around it, so short queries effectively
  get bonus terms to match against, without an explicit thesaurus or
  expansion step.

### Indexing at scale: residual compression and PLAID

Storing one 128-dim vector *per token* instead of *per document* is the
direct cost called out in this week's tasks. A document with 60 tokens now
needs 60 embeddings instead of 1 — roughly a 60x blow-up in raw vector
count before any compression, which is the actual reason ColBERTv2 and
PLAID exist:

- **Residual compression (ColBERTv2)**: cluster all token embeddings in the
  corpus into a modest number of centroids (e.g. 2^18). Store each token
  vector not as a raw 128-dim float array, but as `(nearest centroid ID,
  quantized residual from that centroid)` — the residual needs only 1-2
  bits per dimension instead of 16-32, since it only has to correct the
  centroid, not represent the whole vector. The paper reports roughly a
  6-10x storage reduction versus uncompressed vectors with under 1% quality
  loss.
- **PLAID (Santhanam et al., 2022)** is the query-time engine built on top
  of that compressed index, and what RAGatouille's `.index()` actually
  builds. Retrieval runs in four stages instead of one brute-force MaxSim
  over everything: (1) for each query token, find its nearest centroids —
  cheap, since there are far fewer centroids than documents; (2) use
  *centroid IDs alone* (not full vectors yet) to approximately score and
  prune down to a much smaller candidate set; (3) decompress full residual
  vectors only for the documents that survived pruning; (4) compute exact
  MaxSim over just those decompressed vectors for the final ranking. This
  staged pruning is what makes ColBERT/PLAID viable as a first-stage
  retriever over millions of documents, instead of needing every query to
  brute-force `query_tokens × total_corpus_tokens` comparisons.

### Where ColBERT actually sits in the two-stage story

The natural assumption, coming right off Week 2, is that ColBERT is "a
better reranker" — another Stage 2. It can be used that way, but that
undersells it: because PLAID makes the *document* side fully precomputed
and independently indexable (same structural property a bi-encoder has),
ColBERT can serve as **Stage 1 itself** — replacing the bi-encoder outright,
not just reranking its output. This is the real reason the field cares
about it: it targets cross-encoder-level accuracy at first-stage-retrieval
scale, at the cost of a much larger index than a single-vector bi-encoder.

## Why it matters in production

- **Multi-hop and compositional queries are where pooled vectors quietly
  fail.** A query like "what company did the director of Spirited Away
  found, and what's its most famous film besides that one" has at least
  three distinct sub-claims. A single pooled query vector blends all three
  into one point in embedding space, and a document that's merely
  topically adjacent (anything Ghibli-related) can score almost as well as
  the document that actually answers all three sub-claims — because pooling
  can't tell "generally on-topic" apart from "specifically correct on every
  part." MaxSim scores each sub-claim's best match independently, so a
  document has to actually satisfy *all* of them to accumulate a high sum,
  not just resemble the general topic.
- **Native support is now a checkbox in vector databases, not a research
  curiosity.** Qdrant, Vespa, and Weaviate all ship native multi-vector /
  late-interaction search (Qdrant's is the alternative index store starred
  in this week's resources) — this has moved from "roll your own PLAID
  index" to "a query mode in infrastructure you already run."
- **Storage, not latency, is the capacity-planning line item that changes.**
  Query latency stays close to a bi-encoder's (query-side is still one
  short forward pass); what actually changes cluster sizing math is
  per-token storage at corpus scale — planning for tokens-per-document
  instead of one-vector-per-document changes the math by roughly an order
  of magnitude, and that has to be budgeted before rollout, not discovered
  after.
- **It's a real lever when a cross-encoder Stage 2 is too slow for the
  budget but a bi-encoder alone loses too much recall on compositional
  queries** — exactly the gap between Week 1 and Week 2's architectures
  that this week's model fills.

## Tradeoffs & comparisons

| | Bi-encoder (Week 1) | ColBERT / late interaction (this week) | Cross-encoder (Week 2) |
|---|---|---|---|
| What's stored per doc | 1 pooled vector | 1 vector *per token* (compressed via residuals) | Nothing — recomputed per query |
| Interaction | None — compare two fixed vectors | Late — independent encoding, then token-level MaxSim | Full — joint attention at encoding time |
| Precomputable / indexable | Yes | Yes (this is what PLAID indexes) | No |
| Scales to | Whole corpus | Whole corpus (via PLAID pruning) | Only a small candidate pool |
| Storage cost | Lowest (1 vector/doc) | Much higher (~tokens/doc, compression narrows this) | None (no index) |
| Accuracy | Lowest — single vector must generalize to any query | Closes most of the gap to cross-encoder | Highest — sees the exact pair |
| Typical role | Stage 1 | Stage 1 *or* Stage 2 | Stage 2 only |

Within this week's specific tooling, worth distinguishing:

| | RAGatouille (used this week) | PyLate | Qdrant native multi-vector |
|---|---|---|---|
| Backend | Wraps Stanford's `colbert-ai` + PLAID | Modern, `sentence-transformers`-style API, actively maintained | Multi-vector search built into the DB itself, model-agnostic |
| Status as of this week's build | Works, but pinned to `langchain<1.0` — see pitfalls below | RAGatouille's own stated migration target starting 0.0.10 | No ColBERT training/inference — you still need a model, just not a separate index engine |
| Best fit | Quick from-checkpoint ColBERT experiments | New projects wanting long-term maintenance | Teams already running Qdrant who want late interaction without a second index system |

## Common pitfalls

- **Treating ColBERT as "just a fancier reranker."** Its accuracy makes
  that tempting, but its whole architectural point is that the document
  side is precomputable — it's built to be a first-stage retriever, not
  only a Stage 2 sitting on top of one.
- **Budgeting index storage per document instead of per token.** The naive
  math ("N docs × 1 vector" from Week 1) is off by roughly the average
  token count per document once you switch to ColBERT — plan capacity
  against *token* count, and expect residual compression to claw back
  maybe 6-10x of that, not all of it.
- **Comparing MaxSim scores to cosine similarity by raw magnitude.** As
  shown in the worked example above, MaxSim is a sum over query tokens, not
  a bounded single number — compare rankings, not absolute scores, and
  never across queries of different token counts without normalizing.
- **Assuming "token-level" means "word-level."** Tokens here are
  WordPiece/BPE subword pieces, and each one is *contextualized* by the
  surrounding sentence through the transformer's layers before MaxSim ever
  runs — this is not bag-of-words term matching (that's BM25's job); the
  same subword token gets a different embedding depending on what
  surrounds it.
- **Silently pinning a stale dependency without knowing why.** Building
  this week's project surfaced a real, current example: `ragatouille`
  0.0.9.post2 fails to import against `langchain>=1.0` (LangChain removed
  `langchain.retrievers.document_compressors` in its v1 restructure, and
  RAGatouille never pinned an upper bound). The fix was `langchain<1.0`,
  but RAGatouille also prints its own warning that 0.0.10+ will migrate
  entirely off the Stanford ColBERT backend onto PyLate — pin
  deliberately, and know a library's stated migration path before treating
  a pin as permanent.
- **Not re-indexing after document edits.** Because every token embedding
  is contextualized by the *whole* document at encode time, changing one
  sentence can shift the embeddings of nearby tokens too, not just the
  edited span — there's no cheap partial update the way appending a row to
  a single-vector index is.

## Check yourself

1. Walk through MaxSim by hand for a 3-token query against a document: why
   does each query token independently find its own best-matching document
   token, instead of the whole query being compared to the whole document
   at once? What does that buy you over a pooled bi-encoder vector?
2. Why can ColBERT's document-side embeddings be precomputed and indexed,
   the same way a bi-encoder's can, when a cross-encoder's cannot? What
   specifically differs in how each model processes `(query, document)`?
3. A colleague says "ColBERT's MaxSim score is 8.4 and this document's
   cosine similarity from our old bi-encoder was 0.71, so ColBERT thinks
   it's a much better match." What's wrong with that comparison?
4. Explain, using the multi-hop query example in this file, why a
   single-vector bi-encoder can rank a merely-topical document above the
   one that actually answers every part of a compositional question — and
   why MaxSim structurally avoids that failure.
5. What does PLAID's 4-stage pipeline (centroid lookup → centroid-based
   pruning → decompression → exact MaxSim) buy you over running exact
   MaxSim against every document's full token vectors for every query?
6. This week's actual dependency install broke on `langchain>=1.0`. What
   general lesson does that suggest about adopting a library that ships
   its own "future backend migration" warning, beyond just applying the
   version pin that fixes today's import error?
