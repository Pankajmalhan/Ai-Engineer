# Resources — Week 2: Cross-Encoder Reranking

## From the roadmap

- **Primary**: [Cohere "Reranking" documentation](https://docs.cohere.com/docs/reranking)
  — how the Rerank API works, model choices, and the two-stage retrieval
  pattern it's designed for.
- **Secondary**: [BAAI/bge-reranker-base model card (HuggingFace)](https://huggingface.co/BAAI/bge-reranker-base)
  — the cross-encoder model used by `app/rerankers.py`'s `BGEReranker`.

## Added by Claude (tools named in the roadmap, not in the resource list)

- [Cohere Rerank API reference](https://docs.cohere.com/reference/rerank) —
  exact `client.rerank()` parameters/response shape used in
  `app/rerankers.py`'s `CohereReranker` (`model`, `query`, `documents`,
  `top_n`, `RerankResponse.results[].relevance_score`).
- [sentence-transformers `CrossEncoder` docs](https://sbert.net/docs/cross_encoder/usage/usage.html)
  — `.predict()` / `.rank()` usage for `BGEReranker`.
- [Cohere Rerank pricing](https://cohere.com/pricing) — per-search-unit cost,
  relevant to this week's cost/latency comparison in `concept.md`.
