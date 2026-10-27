# Week 13 -- LangGraph fundamentals

## Overview

Until now the Northwind RAG system has been a function: question in, answer out, nothing
remembered. Real assistants need three things a function doesn't give you: **memory** across
turns, **control flow** richer than a straight line (branches, retries, loops), and a way to
**see inside** a run. LangGraph is a small runtime that provides all three by making you
describe your program as a **graph over a shared state object**. This week is the minimum
useful version: three nodes, one checkpointer, one trace. Later weeks (routing, tool loops,
human-in-the-loop, multi-agent) are this same machinery with more nodes.

## Core concept, in depth

### 1. The mental model: state, nodes, edges, compile

```
            State (MessagesState) -- one shared object
   +-------------------------------------------------+
   | messages: [...]   question: "..."   context: [...] |
   +-------------------------------------------------+
        ^  read          | partial update      ^
        |                v                     |
START -> receive_query -> retrieve_context -> generate_answer -> END
         (node = function)        (edge = "what runs next")
```

- **State** is a typed dict (here `class State(MessagesState)`, a `TypedDict` subclass) -- the
  single source of truth. Nodes don't call each other or pass arguments; they read the state
  and write to it.
- **Node** = a plain function `state -> dict`. It returns only the keys it wants to change (a
  *partial update*), never the whole state. `retrieve_context` returns `{"context": [...]}`
  and nothing else.
- **Edge** = "after A, run B". `add_edge("receive_query", "retrieve_context")`. `START` and
  `END` are the built-in entry and exit. Conditional edges (`add_conditional_edges`) choose
  the next node from the state -- that's where branching and loops come from (not needed
  this week; Week 4's corrective-RAG router is the obvious candidate to port).
- **Compile** (`builder.compile(checkpointer=...)`) turns the builder into an executable.
  It validates the topology (dangling nodes, missing entry) and wires in persistence. Until
  you compile, a `StateGraph` is only a blueprint, which is why `add_node` calls after
  `compile` have no effect.

Execution is organised in **super-steps**: run the node(s) that are ready, apply their
updates to the state, move to the next. With the checkpointer on, a snapshot of the state is
saved after every super-step. That is the whole persistence story; everything below follows
from it.

### 2. Reducers: why `messages` appends and `context` overwrites

This is the one subtle idea in the state definition, and the code in `app/graph.py` uses both:

```python
class State(MessagesState):
    # inherited: messages: Annotated[list[AnyMessage], add_messages]  (reducer: append / merge by id)
    question: str                                         # no reducer: last write wins
    context: list[str]                                    # no reducer: last write wins
```

`MessagesState` is LangGraph's prebuilt state with a single `messages` key already wired to the
`add_messages` reducer -- the long form is `messages: Annotated[list[AnyMessage], add_messages]`,
which you'd write by hand with a plain `TypedDict`. Subclassing it is the idiomatic way to add
your own fields next to the history.

When a node returns `{"messages": [reply]}`, LangGraph doesn't replace the list -- it calls the
reducer `add_messages(old, new)`, which appends. A key with no reducer is simply overwritten.
So `messages` is the **history** (grows each turn) while `question` and `context` are
**per-turn scratch space** (rebuilt each turn). Why this matters in practice:

- Putting retrieved documents into `messages` would make history grow by ~3 documents every
  turn and re-send stale context. Keeping them in `context` means turn 5's prompt contains
  turn 5's documents plus the *conversation*, not turns 1-4's documents. The test
  `test_generate_prompt_contains_context_but_history_does_not` pins this down.
- Forgetting a reducer on a list you meant to accumulate is a classic bug: each turn silently
  throws away the previous contents.
- Parallel branches writing the same key *require* a reducer; otherwise LangGraph raises an
  error rather than guess which write wins.

### 3. Memory = checkpointer + thread_id

```python
graph = builder.compile(checkpointer=MemorySaver())
graph.invoke({"messages": [HumanMessage("...")]}, {"configurable": {"thread_id": "alice"}})
```

On each `invoke`, LangGraph loads the latest checkpoint for that `thread_id`, **merges your
input into it through the reducers**, runs the graph, and saves new checkpoints. So you pass
only the *new* user message; the history comes back from the checkpoint. Consequences worth
internalising:

- `thread_id` *is* the conversation. Same id = same memory; new id = clean slate
  (`test_threads_are_isolated`). In a web app it's your session/conversation id.
- **No checkpointer = no memory**, even though the state schema is identical
  (`test_without_checkpointer_each_call_forgets`). Memory is a property of how you compile
  and call, not of the state definition.
- `MemorySaver` (now also exported as `InMemorySaver` -- same class) keeps checkpoints in the
  process's RAM: perfect for learning and tests, gone on restart, not shared between
  processes. Production swaps in `SqliteSaver` / `PostgresSaver` (or LangGraph Platform's
  managed one) -- *a one-line change at compile time; the graph code is untouched.*
- Checkpoints are queryable: `graph.get_state(config)` returns the current values and what
  runs `next`; `graph.get_state_history(config)` returns every super-step. That's how you
  debug ("what did the state look like when `generate_answer` ran?") and how time travel /
  replay / human-in-the-loop work.
- This is **short-term (thread-scoped) memory**. Cross-thread, long-term memory ("remember
  this customer prefers Spanish next month") is a separate mechanism (the `Store`), not
  covered this week.

### 4. Worked example: the two-turn conversation this week's task asks for

Turn 1, thread `alice`: *"What is the rate limit on the Pro tier?"*

1. `receive_query` copies the last human message into `state["question"]`.
2. `retrieve_context` runs BM25 on it -> `context = ["[rate-limits] ...600 requests...", ...]`.
3. `generate_answer` sends `[system(with context), human]` to the model; the model's reply
   (an `AIMessage` carrying `usage_metadata` token counts) is appended to `messages`.

Turn 2, same thread: *"Repeat the number from your first answer."* The input is one message.
The checkpointer restores turn 1, so `messages` now has `[human, ai, human]`. BM25 on this
question matches nothing useful (no keywords!) so `context` is junk -- but the model still
answers correctly because `generate_answer` passes the **whole `messages` list**, including
its own previous answer. That is exactly "confirm the agent uses context", and also shows the
design's limit: **memory fixes the generator, not the retriever** (see pitfalls).

### 5. LangGraph vs. raw LangChain

| | LangChain (LCEL chain) | LangGraph |
|---|---|---|
| Shape | A pipeline: `a \| b \| c`, data flows left to right | A graph: nodes read/write a shared state, edges route |
| State | Implicit -- only what flows through the pipe | Explicit typed object, with reducers |
| Memory | None built in; you carry history and pass it every call | Checkpointer + `thread_id`, automatic |
| Control flow | Linear (with limited branching) | Branches, loops, retries, cycles are first-class |
| Interruptibility | Run to completion | Pause/resume at any super-step (human approval, long waits) |
| Debugging | Trace of the run | Trace **plus** checkpoint history you can inspect and replay |
| Best for | Fixed, stateless transforms (summarise this, extract that) | Agents, multi-turn assistants, anything with loops or approvals |

`app/lcel_chain.py` is the same retrieve -> prompt -> model pipeline as a chain.
`tests/test_lcel_chain.py` shows it answering a single question fine and then knowing nothing
about the previous call. They're not rivals: LangGraph nodes routinely *contain* LangChain
pieces (this graph's model is a LangChain `ChatOpenAI`, and a node can call a whole chain).
Rule of thumb: if you need to say "and then, depending on the result, go back to step 2",
or "remember this between requests", reach for LangGraph.

**Where Deep Agents fits** (from the roadmap's update note): LangChain's 2026 "Deep Agents"
framework is a higher-level, batteries-included harness (planning, sub-agents, file-system
scratchpad) built *on top of* LangGraph. You'll be debugging it with exactly the vocabulary
above -- state, nodes, checkpoints, traces -- so the fundamentals are the prerequisite, not
something it replaces. **The TypeScript twin**: LangGraph.js has the same concepts
(`StateGraph`, `MemorySaver`, `thread_id` in `configurable`); the Vercel AI SDK solves the
"call a model, stream UI" layer, and is commonly used alongside rather than instead of a
graph runtime. This week's code is Python only.

### 6. Instrumenting with LangSmith

LangSmith needs no code change for LangGraph: set `LANGSMITH_TRACING=true` and
`LANGSMITH_API_KEY` and every `invoke` is traced. What you get, per turn:

- **One trace** (root run) for the graph invocation, with **one child run per node**
  (`receive_query`, `retrieve_context`, `generate_answer`), nested model call under the last.
- **Latency per node**. Expect `receive_query` and `retrieve_context` (in-process BM25) to be
  ~milliseconds and `generate_answer` to be essentially the entire trace. That's the useful
  finding: optimising retrieval is irrelevant to latency here; the model call is the budget.
- **Token counts** on the LLM run (prompt / completion / total), which feed cost. Watch the
  prompt-token count **grow turn over turn on the same thread**: memory is not free, because
  the whole history is re-sent every time. The same trace-reading skill you built with
  Langfuse in Weeks 8 and 12 applies; LangSmith is just the LangChain-native backend, which
  groups runs by node and renders the graph for you.
- Add `tags`/`metadata` (`tracing_context(tags=[...], metadata={"thread_id": ...})` or in the
  `config`) so you can filter traces by conversation.

`scripts/trace_report.py` pulls the same per-node latency and token numbers through the
LangSmith client so you can see them in the terminal as well as the UI.

## Why it matters in production

- **Every serious agent is a loop with state.** Tool-using agents, corrective RAG, approval
  flows: all need "run, look at the result, maybe run again", which a chain can't express.
- **Stateless servers, stateful conversations.** Your Cloud Run service from Week 9 holds no
  state between requests. A durable checkpointer (Postgres, Cloud SQL) keyed by `thread_id`
  lets any instance resume any conversation -- and `MemorySaver` in that setting is a
  *bug*: requests landing on different instances, or after a cold start, would see an
  amnesiac bot.
- **Cost and latency.** History is re-sent each turn, so token cost per turn grows linearly
  and total cost per conversation roughly quadratically. Real systems trim (keep last N
  messages), summarise old turns, or both.
- **Debuggability.** Checkpoint history + traces turn "the bot said something weird" into
  "here is the exact state entering `generate_answer`".

## Tradeoffs & comparisons

- **LangGraph vs. a hand-rolled loop** (`while True: ...` with a dict). For three fixed
  steps, a function is simpler and you should say so. LangGraph earns its keep once you need
  persistence, interrupts, streaming of intermediate steps, or a graph other people can read.
  The cost is a framework to learn and a fast-moving API (docs moved sites, `MemorySaver`
  became `InMemorySaver`, streaming APIs are evolving) -- pin versions.
- **Explicit state vs. convenience.** Typed state with reducers is more ceremony than
  chaining, and it's the price of being able to resume, replay and inspect.
- **Checkpoint everything vs. little.** Every super-step is saved, so large objects in state
  (full documents, embeddings) bloat storage and slow every step. Keep state small; store
  big things elsewhere and keep ids.
- **LangSmith vs. Langfuse** (Weeks 8/12): LangSmith is zero-config with LangGraph and
  understands node structure natively; Langfuse is framework-neutral and self-hostable. The
  data model (trace -> nested spans -> generations with usage) is the same idea.

## Common pitfalls

1. **Forgetting `thread_id`.** With a checkpointer, `invoke` without
   `config={"configurable": {"thread_id": ...}}` raises. A *hard-coded* shared id is worse: all
   your users silently share one conversation.
2. **Passing the whole history in again.** With a checkpointer you pass only the new
   message. Re-sending old messages duplicates them (the reducer appends).
3. **Mutating state in place** (`state["messages"].append(...)`) instead of returning an
   update. It bypasses reducers and checkpoints.
4. **Returning the full state** from a node. Return only changed keys.
5. **Follow-ups break retrieval.** "What about monthly plans?" retrieves fine; "How long do I
   have for *that*?" retrieves noise because BM25 only sees the literal question. Memory
   fixes generation, not retrieval. The standard fix is a query-rewrite step that turns the
   follow-up into a standalone question using the history -- a natural fourth node.
6. **Treating `MemorySaver` as storage.** It's RAM. Fine for the lab; a production bug.
7. **Unbounded history.** Nothing trims `messages` for you; long threads eventually hit the
   context limit or become expensive.
8. **Version drift.** Tutorials on the old docs site use older names and imports. Check
   docs.langchain.com and your installed version.

## Check yourself

1. In `State`, why does `messages` use `add_messages` while `context` has no reducer? What
   would break if `context` were annotated with an appending reducer?
2. You call `graph.invoke` twice with the same input but different `thread_id`s. What does
   each call see, and why? What changes if you compile with no checkpointer?
3. After turn 2, how many checkpoints exist for the thread, and what does
   `get_state_history` let you do that a plain trace cannot?
4. Your LangSmith trace shows `generate_answer` at 1.4 s and `retrieve_context` at 4 ms.
   Where do you look to speed things up, and what happens to prompt tokens as the
   conversation lengthens?
5. When would you pick a plain LCEL chain over a LangGraph graph? Name one requirement that
   forces you to LangGraph.
6. A user says "and what's the limit for the Free tier?" right after a rate-limit answer.
   Does retrieval or generation get this right, and what would you add if it didn't?
