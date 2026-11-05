# Week 16 project -- CrewAI crew vs LangGraph graph, three roles, 20 queries

The Northwind API support assistant built twice from the **same three roles** -- Retriever, Relevance
Grader, Answer Synthesiser -- then compared on 20 complex queries for answer quality and latency.

```
CrewAI    : Crew(sequential) = Retriever agent (tool: search_docs) -> Grader agent -> Synthesiser agent
LangGraph : retrieve (plain function) -> grade (LLM) --(any relevant?)--> synthesise (LLM) | abstain (no LLM)
```

| Piece | Where | What it does |
|---|---|---|
| Roles (single source of truth) | `app/roles.py` | role / goal / backstory for the three roles; CrewAI uses them as `Agent(...)`, LangGraph as node system prompts |
| CrewAI crew | `app/crew_pipeline.py` | 3 agents, `Process.sequential`, task `context` chaining, `output_pydantic=GradeReport`, a `search_docs` tool |
| CrewAI manager crew | `app/crew_manager_pipeline.py` | `Process.hierarchical`: one agentless task, a Support Lead manager delegates to Retriever / Query Rewriter / Grader / Synthesiser and decides the order (incl. one retry) |
| CrewAI Flow | `app/crew_flow_pipeline.py` | `Flow` with `@start` / `@listen` / `@router`: Python routes (incl. one retry), four tiny one-agent crews do the LLM work |
| LangGraph graph | `app/graph_pipeline.py` | same roles; deterministic `retrieve`; conditional edge that skips the synthesiser when nothing is relevant |
| Typed hand-offs | `app/schemas.py` | `Grade` / `GradeReport`, tolerant parsers for passages and JSON |
| 20 queries + answer key | `app/queries.py` | 17 answerable (multi-document, numeric, conditional) + 3 unanswerable |
| Scoring | `app/scoring.py` | fact recall, abstention, retriever recall, grader recall/precision |
| Comparison runner | `app/compare.py` | runs both pipelines on a real OpenAI model, writes `results/comparison-<model>.md` / `.json` |
| Langfuse tracing (optional) | `app/tracing.py` | LangChain callback for LangGraph + OpenInference instrumentor for CrewAI; no-op without keys |

Read [`../concept.md`](../concept.md) first, then [`../decision.md`](../decision.md).

## Install and test

```bash
uv sync                      # core deps (CrewAI is a large install)
uv run pytest -q             # 54 tests, no network, no LLM calls
```

The tests never call an LLM. They check the crew's wiring (agents, tools, task `context`, typed grader
output, one LLM instance per agent), the graph's shape (nodes + conditional abstain edge), the typed
parsers, the 20-query answer key and scorer, and the comparison maths.

## Run the comparison (real LLM)

```bash
cp .env.example .env                       # add OPENAI_API_KEY
uv run python -m app.compare               # gpt-4o-mini, temperature 0, both frameworks
uv run python -m app.compare --model gpt-4o
uv run python -m app.compare --manager     # adds the hierarchical crew as a column (more LLM calls)
uv run python -m app.compare --flow        # adds the CrewAI Flow as a column
```

Output goes to `results/comparison-<model>.md` and `.json` (per-query answers, retrieved/kept ids,
latency, LLM calls, tokens). Both pipelines use the same retriever, role text, model and temperature;
queries run one at a time after an untimed warm-up.

## Trace both pipelines in Langfuse (optional)

```bash
uv sync --extra tracing
# put LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY (/ LANGFUSE_BASE_URL) in .env
uv run python -m app.compare
```

Each query runs inside a span named `crewai:q07` / `langgraph:q07` with tags and a shared session id, so
the two frameworks' traces for the same query sit side by side. `--no-trace` disables it.

## Status

- Verified: all 54 tests; the real OpenAI clients and the crew construct correctly with a placeholder
  key (no network call); tracing degrades to a no-op when keys are absent or setup fails.
- **Not run:** the comparison itself (`python -m app.compare`), so there are **no real quality, latency
  or call-count numbers yet** -- [`../decision.md`](../decision.md) has a table to fill in.
- **Not run:** Langfuse tracing against a live project. `app/tracing.py` follows the Langfuse/OpenInference
  docs and the installed signatures, but CrewAI spans nesting under the per-query span is unverified.
- CrewAI telemetry is disabled in code (`CREWAI_DISABLE_TELEMETRY=true`).
