## Questions

- Late interaction / multi-vector retrieval is genuinely used in industry,
  but I hadn't run into it before -- in what specific circumstances do you
  actually reach for it over plain single-vector (bi-encoder) retrieval?

## Key takeaways

**Single-vector is the default; late interaction is a targeted fix, not an
upgrade.** Most production RAG/search systems run single-vector bi-encoder
retrieval (Week 1), often with a cross-encoder reranker on top (Week 2) --
and that's enough when queries are short, single-concept lookups against
reasonably-sized chunks. Don't reach for multi-vector because it sounds
more sophisticated; reach for it when you've *measured* a specific failure.

**The signal to watch for: compositional queries needing multiple
independent facts satisfied at once.** A pooled vector can't tell
"generally on-topic" apart from "actually correct on every part" -- this is
the exact multi-hop failure mode `concept.md`'s Studio Ghibli worked
example walks through. Concrete production cases where this shows up:

- **Legal/contract discovery** -- "indemnification clause AND governing law
  AND liability cap above $1M" -- each is a distinct sub-claim a pooled
  vector averages together; MaxSim's per-token independence is what
  actually distinguishes documents satisfying all three from documents just
  generally about contracts.
- **Code search** -- a query mixing a specific identifier (`S3Client.putObject`)
  with natural-language intent; the identifier is a small fraction of a
  pooled vector's mass but the whole point of the query.
- **Multi-hop QA over long/technical documents** (medical literature,
  technical manuals) -- passages have to satisfy several independent
  conditions, not just match the passage's "average topic."
- **High query volume where a Stage-2 cross-encoder rerank doesn't fit the
  latency/cost budget**, but bi-encoder-alone recall isn't good enough --
  late interaction targets cross-encoder-level accuracy at first-stage
  scale instead.

Real adopters: **Vespa** ships native ColBERT support for exactly this
class of enterprise/technical search; legal-tech and code-search vendors
are the concrete industry users -- not general-purpose chat-with-your-docs
RAG.

**Where it's not worth it, even though it's "more accurate":**

- Already have a Stage-2 cross-encoder reranker -- stacking an expensive
  multi-vector Stage 1 *and* a cross-encoder Stage 2 is usually redundant
  spend; pick one expensive stage, not two, unless accuracy requirements
  are extreme (legal/medical-grade).
- Storage/ops cost is a real tax -- budgeting per-*token* storage, not
  per-document, plus a specialized index engine (PLAID, or native
  Qdrant/Vespa/Weaviate support) instead of a plain ANN index. Real infra
  and ops burden most teams shouldn't take on speculatively.
- Queries are just simple single-concept lookups and bi-encoder recall@k is
  already >95% on the real query distribution -- nothing to fix.

**Practical rule:** ship single-vector (+ cross-encoder rerank if more
precision is needed) first. Only move to late interaction once specific,
measured queries show that combination failing -- usually compositional/
multi-constraint queries -- and the storage/infra cost is one you're
willing to carry for that gain. It's a targeted fix for pooling's specific
blind spot, not a strictly-better replacement for single-vector retrieval.

## Open threads
