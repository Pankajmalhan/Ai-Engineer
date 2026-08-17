# Resources

## From the brief

- **Chonkie** ★ — fast Python chunking library. https://github.com/chonkie-inc/chonkie
  Used directly for all 6 chunking strategies in `project/app/chunkers.py`
  (`TokenChunker`, `SentenceChunker`, `RecursiveChunker`, `SemanticChunker`,
  `CodeChunker`, `LateChunker`).
- **LlamaIndex `SentenceSplitter`** — the reference implementation this
  week's "sentence-window" and "recursive character" strategies are
  conceptually compared against; see concept.md's tradeoffs section.
- **sentence-transformers** — used to load and run all 3 shortlisted
  embedding models.
- **MTEB leaderboard** — https://huggingface.co/spaces/mteb/leaderboard
  (Retrieval task, models under 500M params). The live Space is a rendered
  JS app that isn't scrapable by a static fetch, so the actual model
  shortlist here came from web search against MTEB-adjacent sources instead
  of a saved leaderboard screenshot -- see concept.md's "Model shortlist"
  section for the specific models, scores, and sources cited per model.
- **W&B (Weights & Biases)** — `chunking_strategy` and `embedding_model`
  logged as run config for every benchmark run; see
  `project/app/wandb_logging.py`. Runs are written offline
  (`./project/wandb/`) since this environment has no `WANDB_API_KEY` --
  run `wandb login && wandb sync wandb/offline-run-*` to push them to your
  own W&B project.
- **pgvector** — not used directly this week (no vector DB in the loop;
  retrieval here is a plain NumPy cosine-similarity search over in-memory
  embeddings, see `project/app/retrieval.py`), but it's the natural next
  step for this pipeline and is what week 1's project already uses.

### Primary

Greg Kamradt's "Chunking Strategies" notebook — 5 methods benchmarked with
recall scores. https://github.com/gkamradt/langchain-tutorials

### Secondary

Muennighoff et al., 2023. *MTEB: Massive Text Embedding Benchmark.*
https://arxiv.org/abs/2210.07316

## Added by Claude (the given set didn't cover Late Chunking's own source)

- Günther et al., Jina AI, 2024. *Late Chunking: Contextual Chunk Embeddings
  Using Long-Context Embedding Models.* https://arxiv.org/abs/2409.04701
  The paper this week's Late Chunking strategy is named after -- read
  before or alongside concept.md's mechanism walkthrough.
- Jina AI's own late-chunking reference implementation/blog:
  https://jina.ai/news/late-chunking-in-long-context-embedding-models/
