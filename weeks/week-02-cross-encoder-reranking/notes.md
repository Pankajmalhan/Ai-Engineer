## Questions

- What actually makes a "bi-encoder" a *bi*-encoder — is it that query and
  document get encoded differently?
- What is NDCG@10, and how is it different from MRR?
- Where does LlamaIndex fit into reranking, and why didn't this project use
  it for Stage 2 instead of hand-rolling `rerankers.py`?
- Besides Cohere, BGE, and LlamaIndex, what other reranking frameworks/APIs/
  models exist?

## Key takeaways

**Bi-encoder naming.** "Bi" = two *independent* encoding passes (encode the
doc at ingest with no query in sight, encode the query at search time with
no docs in sight), compared afterward with a cheap similarity function. It's
not about treating query/doc text differently — a bi-encoder that encodes
both identically is still a bi-encoder. The asymmetric prefixing
`embed_query` vs `embed_passages` uses (see `app/embeddings.py`) is a
*quality trick* some models use, not what defines the architecture. Contrast
with cross-encoder: one *joint* forward pass over `[query, doc]` together,
with attention flowing both directions — that's the real dividing line, not
"same vs. different encoding."

**NDCG@10 vs. MRR.**
- NDCG@10 = DCG@10 / IDCG@10, where DCG discounts each relevant hit by
  `1/log2(rank+1)`. Normalizing by the ideal ordering's DCG (IDCG) turns it
  into a 0–1 score regardless of how many relevant docs exist. Rewards
  *graded* rank quality — rank 1 vs. rank 3 vs. "not in the top 10" all
  score differently, unlike recall@10 which is binary hit/miss.
- MRR = average of `1/rank_of_first_relevant_hit` across queries. Coarser
  than NDCG (only cares about the *first* hit, decays as flat `1/rank`
  instead of `1/log2(rank+1)`, so it punishes a rank 1→2 drop more harshly).
  Right metric when there's exactly one "correct" answer you want as early
  as possible; NDCG is right when rank quality across the whole list matters
  or queries can have multiple relevant docs.
- This project only implements `ndcg_at_k` and `recall_at_k` in
  `app/metrics.py` — MRR is mentioned in `concept.md`'s pitfalls as a
  well-known alternative but not built, since with exactly one relevant doc
  per query (this benchmark's setup) MRR and NDCG would be identical anyway.

**LlamaIndex's reranking abstraction.** LlamaIndex models Stage 2 as a
`BaseNodePostprocessor`: `retriever.retrieve() -> postprocessor
.postprocess_nodes(nodes, query_bundle) -> ...`. Concrete equivalents to
this project's hand-rolled rerankers:
- `SentenceTransformerRerank` (`llama_index.core.postprocessor`) ≈ our
  `BGEReranker`
- `CohereRerank` (`llama_index.postprocessor.cohere_rerank` — a *separate*
  pip package, not installed here) ≈ our `CohereReranker`

Reason this project skipped it: the Cohere postprocessor package was never
added as a dependency, and more importantly, the point of this week was to
see the raw mechanics (pool in → `(query, doc)` pairs scored → reordered
top-N out) without a framework's node/postprocessor object model in the
way. In a real production LlamaIndex-based pipeline, `BaseNodePostprocessor`
is the interface to implement against instead of a custom protocol —
correct choice there is the opposite of the correct choice for this
learning exercise.

**Other reranking options beyond Cohere / BGE / LlamaIndex** (see full
conversation for benchmark sources, current as of research done 2026-08):

- *Orchestration frameworks (LlamaIndex's peers)*: **LangChain**
  (`ContextualCompressionRetriever` + `CohereRerank` or
  `CrossEncoderReranker`), **Haystack** (`Ranker` components).
- *Managed rerank APIs (Cohere's peers)*: **Voyage AI** (`rerank-2.5`,
  bundled with MongoDB Atlas), **Pinecone** (hosted `rerank-v0`, currently
  topping BEIR NDCG@10 benchmarks), **Jina AI** (`reranker-v2`, notably
  fast), **Mixedbread** (`mxbai-rerank`), **AWS Bedrock** (bundles Cohere +
  Amazon rerank models), **Azure AI Search** (built-in semantic reranker).
- *Self-hosted open models (BGE's peers)*: **`BAAI/bge-reranker-v2-m3`** —
  the direct successor to `bge-reranker-base` used in this project;
  multilingual, generally the better default now (a `.env` config swap via
  `BGE_RERANKER_MODEL` if revisited). Also Jina/Mixedbread open weights,
  **ColBERT** (architecturally different — late interaction / token-level
  max-similarity, a speed/accuracy middle ground vs. full cross-encoders),
  **FlashRank** (lightweight, avoids pulling in the full
  `sentence-transformers`/`torch` stack).
- *LLM-based reranking*: prompting an LLM directly to reorder a candidate
  list (LangChain's `RankLLM`/RankGPT-style) instead of using a dedicated
  cross-encoder model — flexible but much slower/costlier; a fallback, not
  a default.
- As of 2026, Cohere's rerank models and `bge-reranker-v2-m3` benchmark
  close to each other on accuracy — the managed-vs-self-hosted tradeoff
  table in `concept.md` is the actual deciding factor, not raw accuracy.

## Open threads

- Cohere path (`CohereReranker`) has never actually been run against the
  real API in this environment — no `COHERE_API_KEY` was available. Code
  matches Cohere's current documented `client.rerank()` signature, but
  worth a real run + a look at real numbers once a trial key is added to
  `.env`.
- Consider trying `BAAI/bge-reranker-v2-m3` (newer/better than the
  `-base` model currently used) via `BGE_RERANKER_MODEL` and comparing.
- MRR isn't implemented — low priority since it would be identical to
  NDCG@10 on this benchmark's single-relevant-doc-per-query setup, but
  would matter if the query set ever grows multi-relevant-doc judgments.
- Not evaluated: LlamaIndex's own `SentenceTransformerRerank`/`CohereRerank`
  postprocessors as a second implementation for comparison against the
  hand-rolled versions (decided against for this week — see Key takeaways).
