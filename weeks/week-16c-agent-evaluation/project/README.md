# Week 16c project -- evaluating multi-agent systems

Trajectory-level evaluation for the agents built in Weeks 14 and 16b. The agents are **not** reimplemented
here: each runs inside its own project through a *bridge* (`bridges/`), prints one JSON trajectory per run, and
everything in `agent_eval/` scores those recordings.

```
agent_eval/trajectory.py       Trajectory / ToolCall -- the one contract (ordered nested tool calls, hand-offs, files, cost)
agent_eval/end_state.py        tau-bench-style tasks: user goal + required end state, as declarative checks
agent_eval/metrics.py          handoff accuracy (+ confusion, subsets), delegation efficiency, pass^k
agent_eval/ragas_metrics.py    RAGAS ToolCallAccuracy / ToolCallF1 (deterministic), AgentGoalAccuracy (LLM judge)
agent_eval/deepeval_metrics.py DeepEval ToolCorrectness (deterministic, via a NoJudge), trajectory metrics, replay-as-trace
agent_eval/compare.py          supervisor-loop vs Deep Agent summary over tasks x trials
agent_eval/gate.py             CI thresholds for the deterministic gates
agent_eval/langfuse_log.py     log a routing run to Langfuse as a dataset run (not run against a live Langfuse)
bridges/w14_route.py           runs the REAL Week 14 graph over the 30 routing queries
bridges/w16b_run.py            runs Week 16b's supervisor loop and Deep Agent over a task file
data/                          routing_30.json, tasks_10.json, hard_5.json, runs/*.jsonl (committed recordings)
scripts/record.py              re-record trajectories via the bridges
scripts/evaluate.py            score recordings (routing report, tool-call metrics, comparison table)
```

## Install, test, run

```bash
uv sync
uv run pytest -q                                # 142 pass; 3 LLM-judged gates skip with an explicit reason
uv run python scripts/evaluate.py routing       # handoff accuracy + RAGAS/DeepEval tool-call metrics + gates on the committed Week 14 run
uv run python scripts/record.py w14             # re-record that run (deterministic: byte-identical)
uv run python scripts/record.py w16b --offline  # scripted t08 only: shows the trajectory shape, nothing about quality
```

Needs a key (`OPENAI_API_KEY`):

```bash
uv run python scripts/record.py w14 --classifier llm
uv run python scripts/record.py w16b --trials 3                       # tasks_10 x {supervisor, deep} x 3
uv run python scripts/record.py w16b --tasks hard_5 --trials 4        # tau-bench-style tasks, for pass^k
uv run python scripts/evaluate.py compare --runs data/runs/w16b_tasks_10.jsonl --tasks tasks_10
uv run python scripts/evaluate.py routing --runs data/runs/w14_llm.jsonl --judge --langfuse
uv run pytest tests/test_agent_gates.py -v                            # DeepEval trajectory metrics + RAGAS goal accuracy gates
```

## What was actually run, and what was not

| Roadmap task | Status |
|---|---|
| RAGAS Tool Call Accuracy / F1 over a W5-style dataset, scored on the W14 supervisor's actual calls | **Run** on the real W14 graph (keyword classifier). *Deviation:* Week 5's dataset is Northwind API Q&A with no tool choice, so the dataset is the same *shape* (`user_input` / `reference` / `reference_tool_calls`) built for Week 14's domain. |
| RAGAS Agent Goal Accuracy | Code written (`score_goal_accuracy`); LLM-judged, **not run** (no key). |
| DeepEval agent metrics as Pytest cases in the Week 6 CI pattern | **Tool Correctness run** (deterministic). Task Completion / Step Efficiency / Plan Quality / Plan Adherence / Argument Correctness: gates written in `tests/test_agent_gates.py`, **never executed with a judge**. Mirrors Week 6's pattern in its own workflow (`.github/workflows/week-16c-agent-eval-gates.yml`) rather than editing Week 6. |
| Handoff accuracy over 30 labelled queries, logged to Langfuse | **Handoff accuracy run** on the real graph. Logging code tested **only against a fake client**; not run against Langfuse. |
| Re-run the W16b supervisor-vs-Deep-Agent comparison with real numbers on 10 tasks, with Step Efficiency | **Not run** -- needs a model. Everything it needs is built and tested (`bridges/w16b_run.py`, `compare.py`, the 10 tasks). One scripted t08 recording shows the shape. |
| Skim tau-bench; write 5 harder end-state tasks | tau2-bench docs read; 5 tasks written and **validated against good, wrong and rephrased answers**, not against a model. |

## Findings so far (real, from the committed Week 14 recording)

```
handoff accuracy 77% (23/30)    by subset: w14 100%, new 65%    recall: code 70%, rules 60%, domain 100%
RAGAS ToolCallAccuracy 0.767 | RAGAS ToolCallF1 0.767 | DeepEval ToolCorrectness 0.767
```

* Week 14's 10/10 does not survive twenty fresh queries (13/20) -- its README warned the number was flattering.
* Every wrong low-confidence guess fell back to `domain`: a systematic bias a single accuracy number hides.
* On a single-hop supervisor the three tool-call metrics equal handoff accuracy -- a pipeline cross-check.
* Measured metric semantics (see `tests/test_tool_call_metrics.py`): an extra tool call is 0.0 / 0.67 / 1.0 in
  RAGAS Accuracy / RAGAS F1 / DeepEval ToolCorrectness; RAGAS tolerates extra *actual* arguments but scores a
  reference's arguments proportionally; DeepEval compares tool names only by default.
* Bugs the tests found in this week's own work: a regex that failed correct "12-hour" answers; a replay/test-case
  that judged the one-line "saved." instead of the saved report.

## Read the numbers carefully

* The gate thresholds sit just under the **keyword baseline**; they guard against regression, not against a bad
  baseline. Re-set them after recording the LLM classifier.
* The committed Week 16b recording is **scripted** (oracle models that only know task t08): it proves the
  trajectory format, the nested-call capture and the scorer -- not that either architecture is any good.
* End-state checks are regexes. They are recall-oriented and can pass a sloppy answer that happens to name the
  right ids; for the real run, read some reports.
* The bridges change nothing in Weeks 14/16b except one deliberate edit at run time: Week 16b's supervisor
  writer prompt is swapped for a neutral one (the original is audit-shaped).
