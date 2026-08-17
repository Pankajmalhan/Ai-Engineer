# Chunking Strategies & Embedding Model Selection

## Overview

Every RAG pipeline makes two decisions before a single query is ever run:
*how do we cut documents into retrievable pieces* (chunking), and *what
model turns those pieces into vectors* (embedding). Both decisions are
usually made once, early, on instinct — "512 tokens with some overlap" and
"whatever embedding model the tutorial used" — and then never revisited,
because by the time retrieval quality problems show up, nobody traces them
back to a chunking boundary or a model choice made weeks earlier.

This week is about making both decisions the way [week 1](../week-01-hybrid-search-rrf/concept.md)
made "does hybrid search actually help": by measuring, on a real corpus,
rather than assuming from a blog post. Six chunking strategies (including
Late Chunking, a 2024 technique that inverts the usual chunk-then-embed
order) get compared with NDCG@10 on a fixed embedding model, then three
MTEB-shortlisted embedding models get crossed against all six strategies to
find which *combination* actually wins — because chunking strategy and
embedding model interact; picking each in isolation can miss that
interaction entirely.

## Core concept, in depth

### Why fixed-size chunking loses context at boundaries

The simplest possible chunker slices text every N tokens, full stop. It
doesn't know what a sentence is, let alone a paragraph, a function, or an
argument. Concretely, with `chunk_size=512`:

```
...the vulnerability affects any server running the outdated TLS handshake.
Administrators should [CHUNK BOUNDARY]
patch immediately, since exploitation requires no authentication and grants
full remote code execution...
```

Two things break here. First, the chunk ending in "Administrators should"
is an incomplete thought — if it's the chunk that gets embedded and
retrieved, its vector represents a sentence fragment, diluted by whatever
came before it, not the actual claim ("patch immediately... remote code
execution"). Second, and more subtly: even the *first* chunk's embedding
never sees the second chunk's content, so a query like *"what happens if
you don't patch this vulnerability"* has to match against a chunk that
never actually says what happens — that information is one token past the
cut.

This is a boundary problem, not a size problem — making chunks bigger just
moves where the cut lands, it doesn't remove the cut. The five
strategies below (Late Chunking is really a sixth category — more on why
below) each attack this differently.

### The six strategies

All six are implemented in [`project/app/chunkers.py`](project/app/chunkers.py)
as thin wrappers over [Chonkie](https://github.com/chonkie-inc/chonkie),
this week's starred resource. `chunk_size=512` (tokens, in the *target
embedding model's own tokenizer* — see `_hf_tokenizer()`) is held constant
across all six so the comparison isolates the splitting *strategy*, not the
size budget.

1. **Fixed-size** (`TokenChunker`) — the naive baseline above: cut every
   512 tokens, no awareness of sentence/paragraph structure. Cheapest to
   compute, worst at boundaries.
2. **Sentence-window** (`SentenceChunker`) — groups whole sentences up to
   the token budget, with a configured sentence-level overlap
   (`chunk_overlap=64` tokens) between consecutive chunks, so a chunk's
   last sentence reappears as the next chunk's first — a cheap way to
   keep the truncated-thought problem from happening at every boundary.
3. **Recursive character** (`RecursiveChunker`) — tries a hierarchy of
   split points (paragraph breaks first, then sentences, then words),
   backing off to a coarser split only when a finer one still produces a
   chunk over budget. This is the same idea as LangChain's
   `RecursiveCharacterTextSplitter`, named in this week's resources — it
   respects the document's own structure where fixed-size ignores it
   entirely.
4. **Semantic** (`SemanticChunker`) — embeds each sentence, then walks
   through the document splitting wherever consecutive sentences' cosine
   similarity drops below a threshold (`threshold="auto"`, a percentile
   computed from the document's own similarity distribution). Chunk
   boundaries land on actual *topic shifts*, not arbitrary token counts —
   at the cost of needing an embedding pass just to decide where to cut,
   before the real indexing embedding pass even starts.
5. **AST-aware** (`CodeChunker`, code docs only) — parses source into an
   Abstract Syntax Tree (via `tree-sitter`) and splits at function/class
   boundaries, so a chunk is never "the last three lines of one function
   plus the first two of the next." There is no AST for prose, so this
   strategy is code-specific by construction — see "Common pitfalls" for
   what this project does with the corpus's text half instead of pretending
   otherwise.
6. **Late Chunking** (`LateChunker`) — see below; it's grouped with the
   other five here because it's still "cut a document into retrievable
   pieces," but the *order of operations* is inverted relative to all five
   above.

### Late Chunking, in depth

This is the strategy the brief calls out as "the 2026 interview signal
that separates tutorial-followers from paper-readers," from Jina AI's 2024
paper *[Late Chunking: Contextual Chunk Embeddings Using Long-Context
Embedding Models](https://arxiv.org/abs/2409.04701)* — worth reading
directly, not just this summary.

**Every strategy above does this:** split the raw text into chunks first,
*then* run each chunk through the embedding model independently. Chunk 3
of 20 gets embedded with zero knowledge that chunks 1-2 or 4-20 exist. If
chunk 3 is "He refused to sign it," the embedding model has no idea *who*
"he" is or *what* "it" is — that context lived in a different chunk that's
already gone by the time embedding happens.

**Late Chunking reorders those two steps:**

1. Run the **entire document** through a long-context transformer in one
   forward pass, producing one embedding vector *per token* (not per
   chunk — the model's own internal token representations, before any
   pooling). Because it's one pass over the whole document, every token's
   representation is contextualized by self-attention over *every other
   token in the document* — "he" and "it" get to attend to the sentence
   that actually named them, wherever it is.
2. *Now* decide chunk boundaries (Chonkie's `LateChunker` uses the same
   recursive splitting logic as strategy 3, just applied to token spans
   instead of raw text).
3. For each chunk's token span, **mean-pool** just that span's token
   embeddings into one chunk vector.

The result: a chunk vector that represents *only* that chunk's text, but
was computed with full-document context baked in via attention, before
pooling ever collapsed anything down. This needs a **long-context
embedding model** — attention has to actually reach across the whole
document, which caps out at whatever context window the model supports
(most standard embedding models max out around 512 tokens; this project's
long-context model, `nomic-ai/modernbert-embed-base`, supports 8192). A
document longer than that window gets silently truncated before pooling —
Late Chunking doesn't remove the context-window ceiling, it just moves
*where* you hit it, from "per chunk" to "per document."

### MTEB and the embedding model shortlist

[MTEB](https://arxiv.org/abs/2210.07316) (Massive Text Embedding
Benchmark) is a standardized suite spanning multiple task types
(Classification, Clustering, Retrieval, STS, Reranking, etc.) across many
datasets and languages, so a single "MTEB score" is really an average
across tasks that don't all matter equally for a given use case. This week
cares specifically about the **Retrieval** task score, not the aggregate.

The brief's instruction was to open the MTEB leaderboard
(huggingface.co/spaces/mteb/leaderboard), filter to Retrieval, filter to
under 500M parameters, and shortlist 3. That Space is a live JS
application with no static leaderboard data in its HTML, so it isn't
fetchable by a plain URL fetch — the shortlist below instead came from
searching for current (as of this week) Retrieval-task standings among
sub-500M models, cited per model:

| Model | Params | Context | Notes |
|---|---|---|---|
| [`BAAI/bge-small-en-v1.5`](https://huggingface.co/BAAI/bge-small-en-v1.5) | 33M | 512 | The week-1 baseline; small, well-established, asymmetric query/passage prefixing. |
| [`nomic-ai/modernbert-embed-base`](https://huggingface.co/nomic-ai/modernbert-embed-base) | 149M | 8192 | ModernBERT-based, natively supported (no custom remote code) — the long-context slot, needed for Late Chunking to mean anything. Chonkie's own `LateChunker` default model. |
| [`Snowflake/snowflake-arctic-embed-m`](https://huggingface.co/Snowflake/snowflake-arctic-embed-m) | 113M | 512 | Snowflake's retrieval-tuned family; Arctic v2.0 reported ~58.4 mean English retrieval score among sub-1B models. |

**A model that didn't survive contact with this environment:**
`jinaai/jina-embeddings-v2-small-en` (33M, 8192 context) is the model
Jina's own Late Chunking reference implementation uses, and was the
original pick for the long-context slot. It requires
`trust_remote_code=True` to load its custom ALiBi attention implementation
from the Hub — and that remote code imports `transformers.onnx` and
`transformers.pytorch_utils.find_pruneable_heads_and_indices`, both of
which have been removed from the `transformers` version this project
pins. This is a real, generalizable risk of `trust_remote_code=True`
models: you're depending on someone else's code staying compatible with a
library version they don't control. `nomic-ai/modernbert-embed-base`
sidesteps the whole problem by using an architecture (ModernBERT) that's
natively built into `transformers` — no remote code, no version-drift risk.

**A caveat worth stating plainly: MTEB's Retrieval task is predominantly
natural-language text**, not code. This project's corpus is half code, and
there's a separate, purpose-built benchmark for that —
[CoIR](https://arxiv.org/abs/2407.02883) (Code Information Retrieval) — that
would be the more defensible leaderboard to shortlist from for a
pure-code corpus. Following the brief's instruction to use MTEB here is a
reasonable starting point for a *mixed* code+text corpus, but "MTEB says
X" is not the same claim as "X is best for code retrieval" — see "Common
pitfalls."

## Why it matters in production

Chunking and embedding-model choice are usually invisible failure modes:
retrieval doesn't error, it just quietly returns *plausible-looking* but
wrong or incomplete results, and nobody thinks to check whether the answer
was ever chunk-boundary-severed from the passage that actually contained
it. This compounds with scale — re-chunking and re-embedding a large
corpus is not a cheap operation to redo after the fact (every chunk's
vector needs recomputing, and depending on the index, rebuilding), so this
is a decision that's expensive to get wrong and expensive to revisit,
which is exactly why it needs measuring up front rather than defaulting to
"512 tokens, whatever model was in the tutorial."

Late Chunking specifically matters in production because most real
documents have exactly the kind of cross-chunk reference problem described
above — a policy doc that says "the exception in section 2 does not apply
here" three paragraphs after defining what "the exception" is; a support
ticket where "the customer" is named once at the top and referred to as
"they" for the rest of the thread. Fixed chunking loses that. Late
Chunking is a genuine, mechanistic answer to it, not just a marginally
better default — which is exactly why it's the technique this week's brief
calls out as the signal for who's actually read the paper versus who's
still doing tutorial-level fixed-size chunking.

## Tradeoffs & comparisons

| | Fixed-size | Sentence-window | Recursive | Semantic | AST-aware | Late Chunking |
|---|---|---|---|---|---|---|
| Respects structure | No | Sentence-level | Paragraph→sentence→word | Topic shifts | Function/class | N/A (chunks after embedding) |
| Cross-chunk context | None | Partial (overlap) | None | None | None | **Full document, via attention** |
| Needs an embedding model to *chunk* | No | No | No | Yes (chunking-time) | No | Yes (chunking-time, same pass as embedding) |
| Chunk count/granularity | Predictable | Predictable | Predictable | **Highly variable** (see measured results) | Predictable (~1/function) | Predictable |
| Compute cost | Lowest | Low | Low | Higher (extra embedding pass) | Low (tree-sitter parse) | Higher (long-context forward pass) |
| Needs long-context model | No | No | No | No | No | **Yes** |
| Applies to code | Poorly (splits mid-function) | Poorly | OK | Poorly (no real "topic drift" in code) | **Best fit** | OK, if within context window |

## Common pitfalls

- **Treating "AST-aware" as if it generalizes to prose.** There's no AST
  for a novel chapter. This project's `ast_aware` strategy dispatches
  per-document: `CodeChunker` for code docs, `RecursiveChunker` as the
  prose fallback (see `chunk_document()` in `chunkers.py`) — a deliberate,
  documented choice, not a silent hack. Applying `CodeChunker` to prose
  (or vice versa) isn't "more thorough," it's a category error.
- **`trust_remote_code=True` is a supply-chain and forward-compatibility
  risk, not just a flag.** See the jina-v2 failure above — remote code you
  don't control can break under a library upgrade you didn't choose, with
  no warning until you try to load it.
- **Assuming late-chunked embeddings inherit the model's asymmetric
  query/passage prefix convention.** They don't, automatically: Chonkie's
  `LateChunker` embeds the raw document text with no prefix, while this
  project's `embed_queries()` still prefixes queries per model (e.g.
  `"search_query: "` for the ModernBERT model). That's a real, structural
  asymmetry between how `late_chunking`'s chunk vectors and every other
  strategy's chunk vectors were produced — worth controlling for before
  treating a late-chunking win or loss as purely about context, and not
  partly about this prefix mismatch.
- **Confusing MTEB's aggregate score with the Retrieval-task score.** A
  model can rank well on MTEB overall while being mediocre specifically at
  retrieval (or vice versa) — always filter to the task that matches your
  use case, not the leaderboard's default sort.
- **Using MTEB to pick a model for a code-heavy corpus without checking
  CoIR.** MTEB Retrieval is overwhelmingly natural-language; a model's MTEB
  rank doesn't promise it's good at matching a docstring-style query to a
  function body. See the "Model shortlist" section above.
- **Not noticing chunk-count blowup from `SemanticChunker` on narrative
  prose.** A document with lots of scene/topic shifts (dialogue-heavy
  fiction, in this corpus) can produce far more, far smaller chunks than
  fixed-size chunking on the same document — see the measured results
  below for exactly how much more. More chunks isn't free: it's more
  vectors to store, index, and search.
- **Silent truncation past a model's context window.** Both
  `SemanticChunker` (per-sentence embedding pass) and `LateChunker`
  (whole-document pass) will silently truncate text past the embedding
  model's max sequence length rather than erroring — this project's own
  corpus has code files and book chapters that exceed even the 8192-token
  long-context model's window (see the `transformers` warning logged
  during the benchmark run). Check your actual document length
  distribution against your model's context window before assuming
  "long-context" means "long enough."

## Measured results on this corpus

*(Filled in after `run_strategy_comparison.py` / `run_model_strategy_grid.py`
finish — see `project/data/part1_strategy_comparison.json` and
`project/data/part2_model_strategy_grid.json` for the full per-query
numbers, and `project/README.md` for the summary tables.)*

## Check yourself

1. A fixed-size chunker with `chunk_size=512` and no overlap splits a
   sentence exactly in half. Which of the six strategies in this project
   would have prevented that specific failure, and by what mechanism (not
   just "it's smarter")?
2. Late Chunking still requires picking a `chunk_size` for the final
   spans. If the whole point is embedding the full document first, why
   does chunk size still matter at all afterward?
3. Why does `SemanticChunker` need an embedding model *before* the
   real indexing embedding pass even happens? What is that first pass
   actually deciding?
4. This project's `ast_aware` strategy silently falls back to
   `RecursiveChunker` for text documents. Give one argument for why that's
   the right default, and one argument for why a project might instead
   want to just skip `ast_aware` scoring entirely on prose documents
   rather than substitute another strategy for it.
5. You have a 20,000-token document and a Late Chunking model with a
   2,048-token context window. What actually happens to tokens 2,049
   onward, and what does that do to the quality of chunks built from that
   part of the document, relative to chunks built from the first 2,048
   tokens?
6. Two embedding models score identically on MTEB's Retrieval task
   average, but one was evaluated primarily on encyclopedic/news text and
   the other on forum/QA text. Your corpus is Python source code. Why
   might neither MTEB Retrieval score actually predict which one performs
   better on your corpus, and what would you check instead?
