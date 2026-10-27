# Week 16b -- Deep Agents: the production agent harness

## Overview

By Week 14 you had a LangGraph **supervisor**: an LLM classifies a query and hands it to one
specialist. By Week 16 you had compared role-based teams (CrewAI) with explicit graphs. Both are ways
to *wire agents together*. A **harness** is a different idea: it is the runtime *around* a single
tool-calling agent loop that decides what the agent can plan with, where it can put things, how it
delegates, and how its context window is kept from filling up. **Deep Agents** (`deepagents`, from
LangChain, built on LangGraph) is a "batteries-included" harness: you call `create_deep_agent(...)` and
get an agent that already has a filesystem, a way to spawn sub-agents, optional planning, and automatic
context management. This week you build the same multi-step task on top of it and on top of your own
supervisor, and learn which of those batteries are worth having.

## Core concept, in depth

### 1. What a harness adds to a bare agent loop

A bare agent is a loop: *model -> (tool calls -> tool results) -> model ...* until the model answers.
Everything else is policy. Deep Agents packages four pieces of policy, each as LangGraph middleware:

| Piece | Mechanism | Problem it solves |
|---|---|---|
| **Virtual filesystem** | `ls read_file write_file edit_file delete glob grep` over a pluggable *backend* | The context window is the only memory of a bare loop. Files give it scratch space and a place to put the deliverable. |
| **Sub-agents** | a `task` tool that spawns a sub-agent with a **fresh context** and returns only its final message | One investigation's raw tool output (a 400-line file, 30 search hits) is useless to the next step but would sit in the thread forever. |
| **Planning** | `write_todos`, a tool whose only effect is to write a todo list into state | Long tasks drift; a visible, editable plan keeps the model on track. It does nothing by itself -- it is a *prompting device*. |
| **Context management** | offloading + summarisation (below) | Long runs hit the window limit. |

> **A correction to the plan text.** The roadmap says "scaffold a minimal deep agent with the default
> planning tool". In the installed `deepagents` (0.7+) `write_todos` is **not** on by default: you add it
> with `middleware=[TodoListMiddleware()]`. The default tool set is the filesystem tools plus `task`.
> (`test_write_todos_is_opt_in_not_a_default` pins this; the project passes the middleware explicitly.)

### 2. Backends: where the "files" live

The filesystem tools talk to a **backend**:

* `StateBackend` (default) -- files live in the LangGraph agent *state*, per thread, checkpointed at every
  step. "Virtual": nothing touches disk. Perfect for a scratch pad; avoid huge files (they are
  checkpointed every step). This project reads the finished report out of `state["files"]["/audit.md"]`.
* `StoreBackend` -- cross-thread storage that survives conversations.
* `CompositeBackend` -- route path prefixes to different backends, e.g. `/memories/` to a store and
  everything else to state.
* `FilesystemBackend` / shell backends -- real disk / real commands. Powerful, and **do not use them in
  a deployed agent**.

Important subtlety: with `StateBackend` the filesystem is **shared** between the lead and its
sub-agents -- a file a sub-agent writes stays in state for the lead to read. So sub-agent *isolation* is
about the **message context**, not the files. That is a feature: a sub-agent can write a 5,000-line
finding to `/notes/code.md` and return the one-line path, keeping even its summary tiny.

### 3. Sub-agents and context isolation -- the heart of the week

The `task` tool takes `description` (the brief) and `subagent_type` (a name). What happens:

1. A sub-agent is built from its spec: `name`, `description` (what the *lead* reads to decide when to
   delegate), `system_prompt`, `tools`, optionally its own `model`. Specified tools **replace** the
   inherited ones; the filesystem tools are still there.
2. It runs with a context containing **only the brief you wrote** (the default `isolated` mode). It sees
   neither the lead's conversation nor the lead's plan nor its siblings' work. (`mode="fork"` opts into
   inheriting the parent's conversation instead.)
3. When it finishes, **only its last message** returns to the lead as the `task` tool result.

Worked through with this week's task. The audit needs the contents of `code/src/auth/session.py`.

* **Supervisor (Week 14, looped):** the code specialist opens the file; the whole file body is
  appended to the one shared thread. Every later supervisor decision, and the final writer, re-reads it.
  Context grows with every hop, and it is never freed.
* **Deep Agent:** the `code-researcher` sub-agent opens the file inside *its* context and replies
  "TTL = 3600, secret hard-coded, `refresh_session` has no type hints". The lead's thread gains ~60
  words, not 60 lines. The test `test_subagent_raw_output_is_isolated_from_the_parent_thread` asserts
  both halves: the raw body is in the sub-agent's prompt and absent from the lead's thread.

Two consequences to design for:

* **The brief is the whole interface.** A sub-agent knows nothing you did not write into `description`.
  "Check the file we discussed" fails; "check `code/src/auth/session.py` against the team rules" works.
* **The summary is lossy by design.** If the sub-agent drops a fact, the lead cannot recover it. Tell the
  sub-agent what to return ("findings only: file:line, rule ids, exact values") and have it keep long
  evidence in a file.

### 4. Context management you get without writing it

* **Offloading** -- when a tool *result* (or a file-write *input*) exceeds a threshold (default 20,000
  tokens), the harness writes it to the backend and leaves a path plus a short preview in the thread; the
  agent can `read_file`/`grep` it later.
* **Summarisation** -- as the thread nears the model's window (around 85%), older history is replaced
  by an LLM-written summary, and the original is preserved as a file.

This is the part a hand-rolled supervisor most obviously lacks: nothing in `app/supervisor.py` prevents
the thread from overflowing. **But the toy corpus here never reaches either threshold**, so this project
cannot show the effect; it only shows isolation. Do not conclude from the project that the harness is
cheaper -- the point is that it *degrades gracefully* when the work gets big.

### 5. Planning (`write_todos`)

The tool takes a list of `{content, status}` items (`pending` / `in_progress` / `completed`). It
performs no work; it makes the plan a first-class object the model re-reads each turn and the
developer can see in `state["todos"]` or a trace. Benefit: fewer skipped steps and drift on long tasks.
Cost: extra turns and tokens, and it is pure overhead for a task of two steps. Which is why it is opt-in.

## Why it matters in production

* **Open-ended work -- coding agents, research, audits, migrations -- is the harness's home.** You cannot
  draw the graph in advance because the number and order of steps depends on what the agent finds.
  A supervisor graph needs you to anticipate the shape; a harness lets the model choose it.
* **Cost and latency are driven by context size**, not step count. Every model call re-sends the whole
  thread, so a thread that carries raw tool output makes *every later call* pricier. Isolation turns
  that from O(steps x everything) into O(steps x summaries).
* **Long runs must survive the window limit.** Offloading and summarisation are the difference between
  "works on the demo" and "works on a 3-hour task".
* **A harness is also a bigger attack surface.** An agent with a filesystem, and especially one with
  `execute`, can do real damage if a retrieved document injects instructions. Pair this with Week 18c
  (sandboxed execution) and Week 23c (agent guardrails); human-in-the-loop is available via
  `interrupt_on={"write_file": True, ...}` (requires a checkpointer), the same mechanism as Week 14's
  approval gate.

## Tradeoffs & comparisons

| | Hand-rolled supervisor (Week 14) | Deep Agent |
|---|---|---|
| Control flow | **You** draw it; deterministic, testable edges | The **model** decides each step |
| Predictability / cost ceiling | High: bounded hops, fixed LLM calls per hop | Lower: number of turns varies run to run |
| Multi-step, unknown-shape tasks | You must add the loop, the planning, the memory | Built in |
| Context growth | Shared thread: grows monotonically | Sub-agent contexts discarded; offloading + summarisation |
| Debuggability | A graph you can read; each edge is yours | A trace of model decisions; more nondeterminism |
| Human-in-the-loop | Native `interrupt()` placement anywhere | `interrupt_on` per tool |
| Overhead on a *small* task | Minimal | Plan + delegation turns you didn't need |
| Failure modes | Mis-routing; stops too early; unbounded loop if you forget the cap | Forgets to save the deliverable; over-delegates; vague briefs; runaway turns |

Rule of thumb: **if you can draw the graph before you run it, draw it** (LangGraph). If the shape
depends on what the agent discovers, reach for a harness. They compose: a LangGraph node can call a
Deep Agent, and a Deep Agent sub-agent can be a compiled LangGraph graph (`CompiledSubAgent`).

## Common pitfalls

* **Assuming planning is on.** It is opt-in; without `TodoListMiddleware` there is no `write_todos`.
* **Handing the lead the tools.** If the lead has the repo tools it will use them itself and the raw
  output lands in *its* thread, defeating isolation. Give tools to sub-agents; give the lead delegation.
* **Vague `task` briefs.** The sub-agent starts from nothing.
* **Not asking for short returns.** A sub-agent that replies with the whole file re-creates the problem
  one level down.
* **Scripted/shared models in tests.** A sub-agent reuses the parent's model *instance* unless you give
  it one; a scripted model then has its script consumed by the wrong agent.
* **`FilesystemBackend`/`execute` in production**, and writing big files to `StateBackend` (checkpointed
  every step).
* **Comparing on a toy corpus.** The harness's context features only matter at scale; a small task will
  flatter the simple graph.
* **Trusting one run.** Agent runs are nondeterministic; compare several.

## Check yourself

1. In `create_deep_agent`, what tools does the lead have by default, and what must you add to get
   `write_todos`? Why does the project deliberately give the lead *no* repository tools?
2. A sub-agent reads a 300-line file and answers in 50 words. Exactly what enters the lead's context, and
   what happens to the 300 lines? What could you do if the lead later needs a specific line?
3. With `StateBackend`, is a file written by a sub-agent visible to the lead? To another sub-agent? What,
   then, is actually "isolated"?
4. Your Week 14 supervisor routed once and answered. Name two things you had to add to make it attempt a
   three-source task, and one problem that remains even after adding them.
5. Using the comparison table, pick the architecture for each: (a) "route a question to the code, rules or
   domain index and return the top hits"; (b) "investigate why p95 latency regressed last week and write up
   findings". Justify with context growth, predictability and cost.
