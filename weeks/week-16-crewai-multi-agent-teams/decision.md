# Decision: LangGraph (control) + CrewAI patterns (role clarity)

**Decision (from the roadmap):** build the assistant on **LangGraph**, borrowing **CrewAI's role
discipline** -- every LLM node gets an explicit role, goal, backstory and output contract, defined once
in [`project/app/roles.py`](project/app/roles.py).

This page records what in *this* project supports that decision, what does not yet, and when to revisit
it. It deliberately separates **measured structural facts** from **numbers that need a real model**.

## What the design gives you (structural, from the code)

| Fact | Where |
|---|---|
| A CrewAI query is expected to take **4 LLM calls** (retriever decide + finish, grader, synthesiser); the LangGraph graph takes **2**, and **1** when the grader keeps nothing | `app/crew_pipeline.py`, `app/graph_pipeline.py` -- confirm the counts in the first real run |
| The retrieval step in LangGraph is a plain function (zero LLM calls); in CrewAI it is an agent that spends two calls to run one search | same files |
| "Abstain when nothing is relevant" is a **conditional edge** in LangGraph (synthesiser never runs) but a prompt instruction in CrewAI (synthesiser always runs) | `test_graph_has_the_expected_nodes_and_conditional_abstain_edge`; crew wiring in `tests/test_crew_pipeline.py` |
| Role text is a single source of truth feeding both frameworks | `test_agent_fields_come_straight_from_the_shared_roles` |
| Each CrewAI agent gets its own LLM instance (a shared one inflates CrewAI's reported usage 3x) | `test_each_agent_gets_its_own_llm_instance` |

## What is NOT yet known (needs the real run)

* **Answer quality**: 20-query correctness and abstention rate for CrewAI vs LangGraph with a real LLM.
* **Real latency, call counts and token cost** per query.
* Whether CrewAI's multi-search Retriever (it may search once per part of a question) actually retrieves
  better than the LangGraph single search -- here BM25 top-4 already covers every expected document, so
  this corpus cannot show it.

Fill this in after `uv run python -m app.compare`:

| | CrewAI | LangGraph |
|---|---|---|
| answerable fully correct (of 17) | _run it_ | _run it_ |
| abstained on unanswerable (of 3) | _run it_ | _run it_ |
| latency mean / p95 | _run it_ | _run it_ |
| LLM calls / tokens per query | _run it_ | _run it_ |

## Revisit the decision if

* The real run shows CrewAI **materially more accurate** (more than a few queries of 20, outside the
  noise of a substring scorer) *and* the gap persists on a larger set -- then the extra calls may be
  paying for themselves, and the fix is to improve the LangGraph prompts/nodes, not to switch.
* The task becomes **open-ended** (the path is not known in advance, roles must negotiate) -- that is
  Crew territory.
* The team wants **CrewAI's ecosystem** (hosted tooling, templates). Then compare against a CrewAI
  **Flow**, which this project did not build.

## What the decision means in practice

1. Keep one `roles.py`; every LLM node's system prompt comes from a `Role` (role, goal, backstory).
2. Keep deterministic steps as plain nodes (retrieval); keep branches as conditional edges (abstain).
3. Give every hand-off a typed contract (`GradeReport`) and a tolerant parser.
4. Trace the graph in Langfuse like everything else; use the CrewAI crew only as a reference
   implementation for the 20-query comparison.
