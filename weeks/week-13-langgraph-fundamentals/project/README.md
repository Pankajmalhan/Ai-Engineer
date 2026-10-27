# Week 13 project -- a stateful LangGraph agent with memory

The Northwind API support bot as a three-node LangGraph:

```
START -> receive_query -> retrieve_context -> generate_answer -> END
```

| Piece | Where | What it does |
|---|---|---|
| State + graph | `app/graph.py` | `State(MessagesState)` (inherited `messages` with the `add_messages` reducer; `question`/`context` overwritten per turn), the three nodes, `build_graph(llm, retriever, checkpointer)`, and `ask(graph, question, thread_id)` |
| Memory | `build_graph(..., checkpointer=MemorySaver())` | Conversation persists per `thread_id`; a different thread starts empty |
| Retrieval | `app/retrieval.py`, `app/corpus.py` | BM25 over the Northwind corpus (same fixture as Weeks 5-12; no embedding cost) |
| LangChain contrast | `app/lcel_chain.py` | Same pipeline as a stateless LCEL chain -- a test shows it forgets between calls |
| Real model | `app/llm.py` | `ChatOpenAI` (needs `OPENAI_API_KEY`) |
| Chat REPL | `app/cli.py` | `uv run python -m app.cli` |
| Multi-turn demo | `scripts/demo_multiturn.py` | Follow-up + "repeat your first answer" on one thread, then the same on a fresh thread |
| LangSmith report | `scripts/trace_report.py` | Per-node latency and token counts for recent traces |

Read [`../concept.md`](../concept.md) first.

## Install and test

```bash
uv sync
uv run pytest -q     # 14 tests, no network, no API keys (uses a recording fake chat model)
```

The tests assert on what the generate node actually sent to the model, so "the agent uses
context" is checked, not assumed.

## Run against the real model

```bash
cp .env.example .env     # fill in OPENAI_API_KEY (and the LangSmith keys below)
uv run python scripts/demo_multiturn.py
uv run python -m app.cli
```

## Trace it in LangSmith

Set `LANGSMITH_TRACING=true` and `LANGSMITH_API_KEY` (in `.env`) and run the demo again. No code
change: LangGraph/LangChain emit traces when those variables are present. In the LangSmith UI,
open the project (`default`, or `LANGSMITH_PROJECT`) and inspect a run: one trace per turn, one
child run per node, and the model call underneath `generate_answer` with its token counts.

```bash
uv run python scripts/trace_report.py --limit 3     # same numbers, in the terminal
```

> Status: the offline suite passes. The real-model demo and LangSmith steps need your keys and
> were not run when this was scaffolded -- run them and note anything surprising in `../notes.md`.
