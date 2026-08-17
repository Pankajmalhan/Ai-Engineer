# Resources — Week 1: Hybrid Search Architecture

## From the roadmap

- **Primary**: [Pinecone blog — "What is Hybrid Search?"](https://www.pinecone.io/learn/hybrid-search-intro/)
  — covers BM25 + dense + RRF in depth.
- **Secondary**: [pgvector GitHub README](https://github.com/pgvector/pgvector) — see
  the "Hybrid search" / full-text search + vectors section.

## Added by Claude (tools named in the roadmap, not in the resource list)

- [ParadeDB `pg_search` docs](https://docs.paradedb.com/documentation/concepts/bm25) —
  the actual extension used for BM25 in this week's project; explains the `@@@`
  operator and `paradedb.score()` used in `project/db.py`.
- [Reciprocal Rank Fusion, original paper (Cormack et al., 2009)](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf)
  — source of the `1/(k+rank)` formula and the `k=60` convention used in
  `project/fusion.py`.
