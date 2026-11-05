# Week 16 -- CrewAI multi-agent teams (role-based) vs LangGraph (graph-based)

## Overview

Week 14 split work by **routing** (a supervisor picks a specialist). This week splits it by
**role**: instead of one prompt that retrieves, judges and writes, you build a small team where each
member has one job -- a *Retriever* that finds passages, a *Relevance Grader* that throws away the
ones that don't help, and an *Answer Synthesiser* that writes the reply from what survived. **CrewAI**
is the framework built around exactly this picture (agents with a role, a goal and a backstory,
working through a list of tasks). **LangGraph** is the one you already know, built around an explicit
graph. The week's real question is not "which is better" but **what does each one cost and buy you** --
so the project builds the same three roles both ways, runs 20 hard queries through each, and the
decision at the end is to use *LangGraph's control with CrewAI's role clarity*.

## Core concept, in depth

### 1. Role-based multi-agent design

A role-based design gives every agent three pieces of text, which together act as its standing
system prompt:

* **role** -- who it is ("Relevance Grader")
* **goal** -- the one outcome it is responsible for
* **backstory** -- the working style, constraints and output format

and (optionally) **tools** it alone may use. The Researcher -> Analyst -> Responder pattern from the
plan is this week's Retriever -> Grader -> Synthesiser. It is also the *corrective RAG* shape from
Week 4: retrieve, **grade**, then generate only from what passed.

Why split one prompt into three roles:

* **Focus.** "Find passages" and "be strict about relevance" and "write a cited answer" pull a single
  prompt in different directions. A grader told only to be strict is stricter.
* **Inspectability.** Each hand-off is a visible artefact (passages, a grade report, an answer), so
  you can see *which role* failed -- the project scores retrieval recall, grader recall/precision and
  answer correctness separately.
* **Swappability.** Each role can use a different model (a cheap one to grade) or be tested alone.

The cost is **more LLM calls**, more prompt tokens carried between roles, and more places for a
hand-off to go wrong. Roles are a design pattern; they are only worth it when each step genuinely
improves the result.

### 2. CrewAI's primitives

| Primitive | What it is | In this project |
|---|---|---|
| `Agent` | role + goal + backstory + tools + an LLM | three agents; only the Retriever has a tool (`search_docs`, BM25) |
| `Task` | one unit of work: description, expected output, the agent doing it, optionally `context=[earlier tasks]` and `output_pydantic` | retrieve -> grade (`output_pydantic=GradeReport`) -> answer (context = retrieve + grade) |
| `Crew` | agents + tasks + a `Process` | `Process.sequential`: tasks run in order, each seeing the context it asked for |
| Tools | `BaseTool` with an input schema and `_run` | `SearchDocsTool` |

There is no graph to draw: **the control flow is "the list of tasks, in order"** (or, with
`Process.hierarchical`, a manager agent that delegates). Hand-offs are text -- one task's output is
pasted into the next task's prompt as context.

**Crews vs Flows.** CrewAI itself has two layers. A **Crew** is the role-based team above: autonomous
agents collaborating on tasks. A **Flow** is CrewAI's event-driven workflow layer: methods decorated
`@start()`, `@listen(other_method)` and `@router(...)` (which returns labels that trigger
`@listen("label")`), with typed state, and Crews can be *called from inside* Flow steps. So CrewAI is
not only "agents chatting": its Flows are the same idea as a LangGraph graph (nodes, conditional
routing, shared state). This week builds a Crew and compares it with LangGraph; "use Flows" is the
CrewAI-native answer to "I need more control", and the honest comparison for a controlled pipeline
is Flows vs LangGraph, which this project does not build.

### 3. What a CrewAI agent actually does per task (observed, not assumed)

Reading the CrewAI loop shows where the time goes:

* **Retriever = two LLM calls for one search.** Call 1: the model decides to use `search_docs`.
  CrewAI runs the tool and appends the result. Call 2: the model finishes ("Final Answer"). The
  decision "search with the user's question" needs no intelligence, yet it costs a model call.
* **Grader = one call**, **Synthesiser = one call** (always, even if nothing was relevant).
* So a query costs **4 LLM calls** in CrewAI.
* Two loop styles exist. With a model that supports function calling (real OpenAI), CrewAI uses
  **native tool calls**; otherwise a text **ReAct** loop (`Thought / Action / Action Input /
  Observation / Final Answer`).
* Token usage is summed **per agent**. If three agents share one LLM object, every call is counted
  three times (4 actual calls would be reported as 12).
  Give each agent its own LLM instance.

### 4. The same roles in LangGraph -- "role clarity" without the overhead

```
START -> retrieve -> grade --(any relevant?)--> synthesise -> END
                       \\--(nothing relevant)--> abstain ------> END
```

* The role **text is shared** (`roles.py`): CrewAI uses it as `Agent(role, goal, backstory)`;
  LangGraph renders it as each node's system prompt. This is the "CrewAI pattern" being borrowed.
* **`retrieve` is a plain function**, not an agent: no LLM call, no tokens, no latency.
* **The conditional edge is control you can read and test**: if the grader keeps nothing, the answer is
  the fixed abstain phrase and the synthesiser is *never called*. In CrewAI the synthesiser always
  runs, and "abstain when nothing is relevant" is a hope expressed in a prompt.
* Result: **2 LLM calls per query** (1 when abstaining) versus CrewAI's 4.

### 5. Worked example (query q01)

*"I'm on the Pro tier and my service had 99.4% uptime last month. What do I get, and how fast will
support respond if I file a ticket about it?"* -- needs `uptime-sla` (99.4% is in the 99.0-99.9% band
-> **10%** credit) **and** `support-sla` (**4 business hours**). BM25 returns four passages; the
grader keeps the three that mention uptime, support and the Pro tier and drops billing. CrewAI runs
4 model calls to get there, LangGraph 2. Whether the final answers match is what the 20-query run measures.

### 6. How the comparison is built, and what it can and cannot say

To make the comparison about orchestration rather than accidents: the **same** retriever (BM25, k=4),
**same** role text, **same** model and temperature, queries run **one at a time** (never concurrently),
an untimed warm-up first, one LLM instance per CrewAI agent, and per-run call/token counting taken
from the frameworks themselves. Scoring is deterministic: each query has an answer key of required
facts (with accepted phrasings), 17 answerable and 3 deliberately **unanswerable** (correct behaviour
= abstain; answering is hallucination).

Limits to keep in mind:

* **n = 20** is a smoke test. A difference of one or two queries is noise.
* **Substring facts** are blind to a fluent answer that states a fact wrongly next to the right one.
* **Retrieval is saturated**: with 8 documents and k=4, BM25 returns every expected document for all
  17 answerable queries. Differences therefore come from grading and synthesis, not search.
* **CrewAI adds its own prompt scaffolding** around the shared role text, so the prompts are not
  byte-identical -- that overhead is part of what is being compared.

## Why it matters in production

* **Latency and cost scale with LLM calls.** A 4-call pipeline is roughly twice as slow and costs
  more tokens than a 2-call one, *before* any quality difference. At ~300 ms per call that is
  roughly 1.2 s vs 0.6 s of model time per query, before CrewAI's own per-call overhead.
* **Determinism and testability.** Control flow in code (LangGraph nodes/edges) can be unit tested
  without a model. Control flow in prompts ("if nothing is relevant, say so") can only be tested by
  paying for real model runs, and drifts when the model changes.
* **Failure containment.** In the graph a malformed grader reply is one caught error in one node.
  In a crew, parsing a task's output (`output_pydantic`) happens inside the framework.
* **Observability.** Both frameworks can be traced into one Langfuse project (LangChain callback for
  LangGraph, an OpenTelemetry instrumentor for CrewAI), so you can compare a CrewAI trace and a
  LangGraph trace of the same query side by side.
* **Privacy default.** CrewAI sends anonymous usage telemetry unless disabled
  (`CREWAI_DISABLE_TELEMETRY=true`). The project turns it off; check this on any framework you adopt.
* **Churn.** CrewAI's surface moves quickly (the loop internals, deprecation warnings on every Agent
  build in this version). Pin versions.

## Tradeoffs & comparisons

| | CrewAI Crew | CrewAI Flow | LangGraph |
|---|---|---|---|
| Mental model | a team of role-playing agents | event-driven steps (`@start/@listen/@router`) | explicit graph of nodes and edges |
| Control flow | task order (or a manager agent) | code, with routers | code, with conditional edges |
| Time to first working version | fastest | medium | slower (you draw it) |
| Hand-offs | text pasted into the next prompt | typed state | typed state |
| Deterministic steps (a retrieve that needs no LLM) | still an agent loop | a plain method | a plain node |
| Skip a step when it adds nothing | prompt it | `@router` | conditional edge |
| LLM calls for this pipeline | 4 | ~2 (if built that way) | 2 (1 on abstain) |
| Best at | exploratory, open-ended collaboration; prototypes | production pipelines in the CrewAI ecosystem | production pipelines needing control, persistence, human-in-the-loop (Weeks 13-14) |

**When to use which**

* Reach for a **Crew** when the path is not known in advance, roles genuinely differ, and you want
  speed of prototyping over control.
* Reach for **LangGraph** (or a CrewAI Flow) when the steps are known, some are deterministic, you need
  to skip/branch/loop on conditions, pause for a human, or test the control flow.
* The week's decision -- **LangGraph with CrewAI patterns** -- keeps what CrewAI is good at (a clear
  role, goal and output contract per step, in one shared `roles.py`) and what LangGraph is good at (a
  deterministic, testable skeleton).

## Common pitfalls

1. **Sharing one LLM object across CrewAI agents** -- usage metrics are summed per agent, so calls are
   counted 3x. One instance per agent.
2. **Comparing frameworks with different retrievers, k, models or temperatures** -- then you are
   measuring the setup, not the framework.
3. **Timing the first query** -- import and first-call costs land on query 1. Warm up, and run
   sequentially.
4. **Letting an LLM make a decision that is not a decision** (calling a search tool with the user's
   own question). It buys latency and failure modes, not quality.
5. **Putting control flow in prompts** and calling it a safeguard ("if nothing is relevant, say you
   don't know"). Enforce it in code where you can.
6. **Brittle hand-off parsing.** Models wrap JSON in code fences and prefix passages with bullets;
   the project's parsers tolerate both (a real first-line bug was caught by exactly this).
7. **Trusting a 20-query substring score** to rank frameworks by a point.
8. **Forgetting framework telemetry** is on by default.
9. **Believing "more agents" means "better answers".** Each extra role has to earn its calls.

## Check yourself

1. Name the three pieces of text that define a CrewAI agent, and say how this project makes the
   LangGraph nodes use the *same* role definitions.
2. A Crew answers a query with 4 LLM calls and the LangGraph graph with 2. Account for every call in
   both, and explain why the graph can sometimes use only 1.
3. Where in this pipeline is control flow written in *code* and where in a *prompt* -- for each
   framework? Give one failure that is easy to unit test in one and hard in the other.
4. What would you need to run to compare real answer quality, and why is a 20-query substring score only
   a smoke test?
5. CrewAI also has Flows. What is the difference between a Crew and a Flow, and which one would you
   compare with LangGraph for a fixed three-step pipeline?
6. You see "mean 12 LLM calls" for a 4-call CrewAI run. What is the most likely cause and the fix?
