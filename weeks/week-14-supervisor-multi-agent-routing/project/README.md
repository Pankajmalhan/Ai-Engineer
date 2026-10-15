# Week 14 project -- supervisor routing with human-in-the-loop

A LangGraph supervisor that classifies a query into **code / rules / domain**, routes it to one of
three sub-agents (each backed by a stub retrieval function), and **pauses to ask a human** when its
confidence is below 0.6.

```
START -> receive_query -> supervisor --(Command goto)--> code_agent   -> END
                            ^   |                        rules_agent  -> END
                            |   v                        domain_agent -> END
                            clarify  (interrupt)
```

| Piece | Where | What it does |
|---|---|---|
| Contracts | `app/schemas.py` | Pydantic `Route(category, confidence, reasoning)`; `CONFIDENCE_THRESHOLD = 0.6` |
| Supervisor brains | `app/classifiers.py` | `LLMClassifier` (`with_structured_output(Route)`) and an offline `HeuristicClassifier` keyword baseline, same `classify(query) -> Route` interface |
| Sub-agent stubs | `app/retrievers.py` | `search_code`, `lookup_rules`, `search_domain_docs` return labelled canned hits (real indexes: Month 5) |
| Graph | `app/graph.py` | supervisor / clarify / three agents; `ask()` and `resume()` helpers; optional `require_approval=True` gate before each retrieval |
| Routing eval | `app/routing_eval.py` | 10 queries (8 clear, 2 ambiguous with scripted human replies) run end-to-end through the graph |
| Scripts | `scripts/eval_routing.py`, `scripts/demo_hitl.py` | Print the eval table; interactive clarification + approval demo |

Read [`../concept.md`](../concept.md) first.

## Install and test

```bash
uv sync
uv run pytest -q        # 26 tests, no network, no API keys
```

Tests assert behaviour, not just "it runs": which retriever was called (and that the others
weren't), that the graph is paused at `clarify` with nothing retrieved yet, that the classifier is
*not* re-run when the human answers a clarification, that a rejected approval never calls the
tool, that the clarification loop is bounded, and that a second turn on the same thread starts
with fresh routing state.

## Routing eval

```bash
uv run python scripts/eval_routing.py                    # keyword baseline, offline
uv run python scripts/eval_routing.py --classifier llm   # real supervisor (needs OPENAI_API_KEY)
```

Reports final accuracy, whether the supervisor asked on exactly the ambiguous cases, and
first-pass accuracy on the clear cases. Offline baseline result: 10/10, 10/10, 8/8.

**Read that number carefully.** The keyword lists were written by the same person who wrote the 10
queries, so the baseline is flattering, and ten cases can't separate good routers from great ones.
The useful comparison is `--classifier llm` against the baseline on queries you didn't write.

## Try the interrupts by hand

```bash
uv run python scripts/demo_hitl.py
# you> Tell me about session refresh      -> supervisor asks (confidence 0.20)
# you> the implementation                 -> re-routed to code_agent
# approve? [y/N] y                        -> retrieval runs (n = "rejected by the user")
```

## LLM run and tracing

```bash
cp .env.example .env     # OPENAI_API_KEY; add the LangSmith keys to trace runs
```

With `LANGSMITH_TRACING=true` every run is traced with no code change; look for `supervisor`,
`clarify` (the paused run and the resumed one) and the chosen agent as separate spans.

> Status: the offline suite and the offline eval pass. The LLM classifier path is covered only by a
> stubbed-model unit test -- it was **not** run against a real model here (no API key). Run the
> `--classifier llm` eval and record the accuracy and any miscalibrated confidences in `../notes.md`.
