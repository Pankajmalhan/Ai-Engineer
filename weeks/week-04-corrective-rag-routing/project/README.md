# Week 4 project — query router + Corrective RAG

Implements two of the three weekly goals end to end, checked against the CRAG
reference at
[NirDiamant/RAG_Techniques/crag.ipynb](https://github.com/NirDiamant/RAG_Techniques/blob/main/all_rag_techniques/crag.ipynb).
The third (DSPy prompt optimization) is **deferred** -- concept.md doesn't cover it
either right now; revisit both together once you've learned DSPy separately.

1. **Query router** (`app/router.py`) — `SemanticRouter` classifies a query as
   FACTUAL / CODE / CONVERSATIONAL (TF-IDF-similarity-to-~25-prototypes/class + a
   code-heuristic booster) and dispatches to the matching retrieval strategy.
   `CascadingRouter` wraps it with a production-shaped second tier: only the
   low-confidence minority gets escalated to `LLMRouteClassifier` (a real LLM call)
   instead of silently defaulting, and every escalation is logged to
   `router_escalations.jsonl` so it can be reviewed and folded back into the
   prototype set, shrinking the escalation rate over time.
2. **Corrective RAG** (`app/crag.py`) — retrieves via `hybrid_search`
   (`app/retrieval.py`, BM25 + real pgvector embeddings, RRF-fused), grades every
   chunk 0-1 (`app/grader.py`), and branches on the paper's actual **dual threshold on
   the max chunk score**: `> 0.7` Correct (refine and keep retrieval), `< 0.3`
   Incorrect (discard retrieval, rewrite the query, web search), otherwise Ambiguous
   (refine retrieval **and** web search, combine). Refined context
   (`app/refiner.py`, decompose-then-recompose) is generated into a final answer
   (`app/answerer.py`).

`app/pipeline.py` wires both into one `QueryPipeline.handle(query)` call.
`concept.md` (one level up) explains the mechanics and tradeoffs in depth.

## What's real vs. a stand-in

- `hybrid_search` is real: BM25 (`rank-bm25`) fused with real dense embeddings
  (`BAAI/bge-small-en-v1.5` via sentence-transformers) stored in a real Postgres +
  pgvector instance, combined by reciprocal rank fusion. Both the FACTUAL and CODE
  routes call it against different pgvector *collections*, with CODE weighting BM25
  more heavily (exact identifiers/error strings matter more there than semantic
  similarity) -- see concept.md for why this replaces a separate ColBERT-backed CODE
  route rather than standing up a second retrieval stack.
- Every CRAG step (grade / refine / rewrite / answer) has **two** implementations
  behind the same interface: a free, deterministic, offline heuristic (`Heuristic*`,
  `Extractive*`) and a real LLM-backed one (`LLMGrader`/`LLMRewriter`/`LLMRefiner`/
  `LLMAnswerer`), all plain Instructor + Anthropic calls -- a hand-written prompt, the
  same shape as the reference notebook's `retrieval_evaluator`. The heuristics are
  genuinely simplified relative to an LLM at the same job (see concept.md's grader
  comparison) -- they are not stubs, they're the actual code path that runs with no
  API key.
- `LocalFallbackSearch` is a small static offline snapshot standing in for real web
  search (`TavilySearch`), used so the whole retrieve→grade→escalate→answer loop (and
  its tests) run with zero network calls by default.

Set `ANTHROPIC_API_KEY` to use the real `LLMGrader`/`LLMRewriter`/`LLMRefiner`/
`LLMAnswerer`, and `TAVILY_API_KEY` to use real `TavilySearch`, instead of the offline
stand-ins.

## Setup

```bash
cd project
docker compose up -d   # starts Postgres + pgvector on localhost:5433
uv sync                 # installs deps into .venv (or: python -m venv .venv && pip install -e .)
```

Optional, for the real (non-heuristic) grader/refiner/rewriter/answerer and real web search:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export TAVILY_API_KEY=tvly-...
```

Neither is required for the demo or the tests -- only Postgres (via
`docker compose up -d`) is required; the LLM/web-search keys only unlock the real
(non-heuristic) code paths.

## Run it

```bash
uv run python -m app.demo
```

Routes four sample queries (factual/code/conversational/out-of-domain), shows each
one's CRAG action (Correct/Incorrect/Ambiguous), refined context, and final answer.
If `ANTHROPIC_API_KEY` is set, it then re-runs the same queries with the real
`LLMGrader` wired in, so you can compare the heuristic and LLM-as-judge grading
decisions directly. It then runs `CascadingRouter` against a couple of genuinely
ambiguous queries and reports its escalation rate -- with `ANTHROPIC_API_KEY` set,
watch it actually escalate to `LLMRouteClassifier` and write to
`router_escalations.jsonl`.

## Tests

```bash
uv run pytest
```

Most tests are fully offline (`HeuristicGrader`/`HeuristicRefiner`/
`HeuristicRewriter`/`ExtractiveAnswerer` and `LocalFallbackSearch` stand in for
network calls). Tests that exercise `hybrid_search`/`PGVectorStore`/the full pipeline
need the `docker compose up -d` Postgres and are marked `@requires_postgres`
(`tests/conftest.py`) -- they **skip** cleanly with a message if it isn't reachable,
rather than failing.

Covers the router's classification and low-confidence fallback, `CascadingRouter`'s
escalation branching and JSONL logging (`tests/test_cascading_router.py`, using fakes
so it doesn't depend on real TF-IDF scores landing above/below a threshold by chance),
hybrid retrieval against a real pgvector store, the grader (bounds validation
included), the query rewriter and knowledge refiner, CRAG's full
Correct/Incorrect/Ambiguous branching (including the mean-vs-max dilution edge case
concept.md's Check Yourself Q1 asks about), web search, and the end-to-end pipeline.
