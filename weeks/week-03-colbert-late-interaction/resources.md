# Resources — Week 3: ColBERT & Multi-Vector Retrieval

## From the roadmap

- **Primary**: [ColBERT paper (Khattab & Zaharia, 2020) — SIGIR](https://arxiv.org/abs/2004.12832)
  — skim Sections 1–3 for the late-interaction architecture and MaxSim
  scoring this week's `concept.md` walks through.
- **Practical**: [RAGatouille GitHub README](https://github.com/AnswerDotAI/RAGatouille)
  and its notebook examples — the wrapper used in `project/` to index and
  search with ColBERT without driving the original Stanford CLI directly.
- Tools named in the roadmap block: **ColBERT**, **RAGatouille**,
  ⭐ **Qdrant** (alternative multi-vector index store to PLAID), **PyLate**.

## Added by Claude (tools named in the roadmap, not linked in the resource list)

- [ColBERTv2 paper (Santhanam et al., 2021)](https://arxiv.org/abs/2112.01488)
  — introduces the residual compression this week's `concept.md` describes;
  `colbert-ir/colbertv2.0` (the checkpoint `project/` loads) is this paper's
  released model.
- [PLAID paper (Santhanam et al., 2022)](https://arxiv.org/abs/2205.09707)
  — the 4-stage retrieval engine (centroid pruning → decompression → exact
  MaxSim) that RAGatouille's `.index()` builds under the hood; explains the
  storage/latency trade this week's memory-profiling task measures.
- [PyLate documentation (LightOn)](https://lightonai.github.io/pylate/) —
  the actively-maintained, `sentence-transformers`-style ColBERT library
  RAGatouille's own README states it is migrating onto starting at
  `0.0.10`. Worth a look if extending this week's project past a
  from-checkpoint experiment.
- [Qdrant multi-vector / ColBERT support docs](https://qdrant.tech/documentation/concepts/vectors/#multivectors)
  — the starred alternative to a standalone PLAID index: late-interaction
  search as a native mode in a vector DB you might already be running.
- [RAGatouille GitHub issues on `langchain` compatibility](https://github.com/AnswerDotAI/RAGatouille/issues)
  — background for the real dependency break this week's project hit
  (`langchain>=1.0` removed the module `ragatouille` imports at startup);
  see `project/README.md`'s Setup section and `concept.md`'s pitfalls.
