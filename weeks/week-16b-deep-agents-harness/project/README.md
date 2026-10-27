# Week 16b project -- Deep Agent vs the Week 14 supervisor

One multi-step task, three architectures, one table.

**The task** ([`app/task.py`](app/task.py)): *audit the session-refresh feature* of a small mock repo --
(1) find the implementation and tests, (2) check them against the team rules and list violated rule
ids, (3) compare behaviour with the documented session policy. The answer needs **code + rules +
domain docs**; no single source can answer more than half of it (a test asserts this).

| Architecture | What it is | Code |
|---|---|---|
| `supervisor, 1 hop` | Week 14 as written: classify, route to ONE specialist, answer | [`app/supervisor.py`](app/supervisor.py) with `max_hops=1` |
| `supervisor, loop` | the same supervisor allowed to hop until it says `finish`; specialists are fixed retrieval functions; one shared thread | `max_hops=6` |
| `deep agent` | [`deepagents`](https://github.com/langchain-ai/deepagents): planning (`write_todos`), three sub-agents via `task`, virtual filesystem; the lead has **no repo tools**, so it must delegate | [`app/deep.py`](app/deep.py) |

```
app/corpus.py     the mock repo (code / rules / docs) + keyword retrieval
app/tools.py      LangChain @tool wrappers (used by the Deep Agent's sub-agents)
app/task.py       TASK + a 6-fact regex scorer (recall only -- see its docstring)
app/supervisor.py Planner/Step/LLMPlanner + the looping LangGraph supervisor
app/deep.py       build_deep_agent(): lead + code-researcher / rules-checker / policy-analyst
app/metrics.py    callback counters: LLM calls, tool calls, tokens, parent-thread size
app/runners.py    run_supervisor / run_deep -> the same RunResult
app/offline.py    scripted chat models + "oracle" responders (no API key)
app/compare.py    the table
```

## Install, test, run

```bash
uv sync
uv run pytest -q                        # 40 tests, no network, no API keys
uv run python -m app.compare --offline  # scripted models: proves the plumbing
cp .env.example .env                    # add OPENAI_API_KEY
uv run python -m app.compare            # the real comparison
```

Offline output (scripted -- read the caveat below):

```
architecture             facts  llm tools   tokens thread chars   secs  report
supervisor, 1 hop          1/6    1     1      n/a         2139    0.0  final-message
supervisor, loop (<=6)     6/6    1     3      n/a         3752    0.0  final-message
deep agent                 6/6   14    10      n/a         2977    0.0  file
```

## What the tests establish

* The lead is handed `task`, `write_file`, `ls`, `write_todos`... and **none** of the repo tools; each
  sub-agent gets exactly its own repo tools.
* `write_todos` is **opt-in** (`TodoListMiddleware`) in the installed `deepagents`; the roadmap's
  "default planning tool" is out of date. `test_write_todos_is_opt_in_not_a_default`.
* **Context isolation, both sides:** the code-researcher's context contains the raw file body; the lead's
  thread never does -- only the sub-agent's summary crossed back. A sub-agent also cannot see its
  siblings' work or the lead's plan.
* Callbacks reach inside sub-agents, so `llm_calls` (14) is more than the AI messages in the lead's thread.
* The supervisor loop stops at the hop cap even when the planner never says `finish`; one hop provably
  cannot cover a three-source task (1/6).
* Failure modes are reported, not crashed on: a report given in chat but never saved is flagged
  `final-message (not saved)`; a runaway agent becomes `error: GraphRecursionError`.
* Two deliberate breakages were checked against the suite: removing the hop cap, and giving the lead the
  repo tools, each fail a test.

## Read the numbers carefully

> **Status: the offline suite and the offline table pass. Nothing here has been run against a real
> model** (no `OPENAI_API_KEY` in the environment that built this).

* Offline scores are **by construction**: the oracle responders only say a finding if the real tools
  surfaced its evidence, so they validate retrieval and wiring, not model quality. Tokens are `n/a`.
* The corpus is ~10 small files. The harness's big-context features -- offloading tool results over
  20,000 tokens, summarising at ~85% of the context window -- **never trigger** here. Expect the
  Deep Agent's overhead (plan + delegation turns) to show up and its context savings mostly not, until
  the corpus is large.
* One run per architecture is anecdote. LLM runs vary; repeat before believing a gap.
* The scorer is recall of named facts. It cannot tell "SEC-03 is violated" from "SEC-03 exists", so read
  the reports (the Deep Agent's is in the final state at `/audit.md`).

After the first real run, fill in the table in [`../decision.md`](../decision.md) and the questions in
[`../notes.md`](../notes.md).
