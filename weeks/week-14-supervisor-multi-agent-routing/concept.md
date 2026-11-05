# Week 14 -- Supervisor pattern and multi-agent routing

## Overview

One agent with one big prompt and every tool attached gets worse as you add capabilities: the
prompt bloats, tool choice gets noisy, and you can't test or improve one capability without
disturbing the others. The **supervisor pattern** splits the job: a top-level model does only
one thing -- decide *who* should handle this request -- and hands off to a specialist that owns a
narrow prompt and its own retrieval/tools. This week the supervisor classifies a query into
**code / rules / domain**, three stub-backed sub-agents answer, and when the supervisor isn't
sure (confidence < 0.6) the graph **pauses and asks a human** instead of guessing. That pause is
LangGraph's human-in-the-loop primitive, `interrupt()`.

## Core concept, in depth

### 1. What a supervisor is (and the three shapes it comes in)

| Shape | Control flow | When it fits |
|---|---|---|
| **Router** (this week's build) | supervisor picks a specialist once, specialist answers, done | queries are independent and each fits one specialist -- the common RAG case |
| **Supervisor loop** | specialist returns to the supervisor, which may call another, then synthesises | one question needs several specialists ("is this function allowed under our rules, and what does the billing term mean?") |
| **Handoff / swarm** | agents pass control to each other directly, no central node | the next step is best judged by the agent that just acted; less central control, harder to debug |

Our graph is a router. The supervisor *could* become a loop by replacing each `agent -> END`
edge with `agent -> supervisor` plus a "done" route -- a worthwhile extension, but only worth the
extra latency when single-specialist answers demonstrably fail.

Two ways to wire the supervisor:

1. **As a node that returns `Command(goto=...)`** (what we build). The supervisor is plain code
   around one model call; routing is explicit and testable.
2. **Sub-agents as tools of a supervisor agent.** The supervisor is a tool-calling agent; each
   specialist is wrapped in a tool (`ask_code_expert`, ...) and the model picks by tool
   description. Less code, handles multi-specialist questions naturally, but routing is implicit
   in tool-calling behaviour, so you have less to unit-test and fewer places to put a threshold.
   LangGraph's current subagent docs show this shape, and the older `langgraph-supervisor`
   package packages it.

For a *classification* decision with a confidence gate, (1) is the better fit: you need the label
and the confidence as data, not as a side effect of a tool call.

### 2. The supervisor node, mechanically

```python
class Route(BaseModel):                       # Pydantic: the contract
    category: Literal["code", "rules", "domain"]
    confidence: float = Field(ge=0, le=1)
    reasoning: str = ""

def supervisor(state) -> Command[Literal["code_agent", "rules_agent", "domain_agent", "clarify"]]:
    route = classifier.classify(state["query"])             # llm.with_structured_output(Route)
    uncertain = route.confidence < 0.6 and state["clarifications"] < MAX
    return Command(update={"route": route.model_dump()},
                   goto="clarify" if uncertain else f"{route.category}_agent")
```

* **Structured output** constrains the model to the `Route` schema, so `category` can't be
  "maybe code?" and a typo fails validation instead of routing into a void.
* **`Command(update=..., goto=...)`** lets one node write state *and* choose the next node.
  Use it when you need both; use a conditional edge when you only route. The return annotation
  `Command[Literal[...]]` is not decoration -- `goto` is decided at runtime, so this annotation is
  the only way LangGraph learns, at compile time, which nodes this node can send control to.
  Without it the graph still *runs* correctly, but the compiled structure is wrong: drawings
  (`get_graph().draw_mermaid()`, Studio) show the node going straight to `END` with no arrows to
  its real targets.
* **Gotcha:** `Command` adds *dynamic* edges on top of any static `add_edge` from the same node.
  Give a node either static edges or `Command`, never both, or both targets run.

### 3. Where the confidence number comes from -- and why not to trust it blindly

The task says "when confidence < 0.6". That number has to come from somewhere:

* **Verbalised confidence** (the model writes `0.85` in the schema) -- what we do. Cheap and
  works as a *coarse* signal, but LLMs are overconfident and clustered (0.8-0.95 for nearly
  everything). Treat 0.6 as a starting guess and **calibrate it**: run labelled queries, plot
  confidence against correctness, and pick the threshold from the data.
* **Token log-probabilities** of the category token -- better calibrated where the provider
  exposes them.
* **Embedding margin** -- similarity to each specialist's example queries; low top-1 minus top-2
  gap means ambiguous. Cheap, no LLM call.
* **Agreement** -- classify several times / with several models; disagreement = low confidence.

A useful prompt instruction (we use it): *"if the question could belong to two specialists, give
a LOW confidence rather than guessing."* It makes the number mean "is this ambiguous?", which is
exactly what we want to gate on.

The offline `HeuristicClassifier` shows the same idea with keywords: confidence is **how
one-sided the evidence is, discounted when there's little of it**. No evidence -> 0.2; evidence
split across categories -> low; two clean matches -> 1.0.

### 4. Human-in-the-loop: `interrupt()` and `Command(resume=...)`

Three ingredients, all required:

1. A **checkpointer** on `compile(checkpointer=...)` -- the pause *is* a saved checkpoint.
2. A **`thread_id`** in the config -- the pointer to which saved state to continue.
3. **`interrupt(payload)`** inside a node -- stops the graph and surfaces `payload` to the caller
   (JSON-serialisable; ours is `{"type": "clarification", "question": ..., "options": [...]}`).

```python
# first call: runs until interrupt, returns control to you
result = graph.invoke({"messages": [HumanMessage(q)]}, config)
result["__interrupt__"][0].value        # -> the payload; show it to the human

# later (seconds or days, even another process if the checkpointer is durable):
graph.invoke(Command(resume="rules"), config)   # "rules" becomes interrupt()'s return value
```

**The rule that bites everyone:** on resume, the interrupted node **re-runs from its first
line**; `interrupt()` just returns the resume value this time instead of pausing. So code above
the `interrupt()` runs twice. Design for it:

* Keep nodes with an interrupt **small, with nothing expensive or non-idempotent above it**. That
  is why classification (an LLM call) sits in `supervisor` and the interrupt sits in a separate
  `clarify` node. A test asserts the classifier is *not* re-invoked when the human answers.
* Never send an email / charge a card / write a row above an `interrupt()` in the same node.
* If a node has several `interrupt()` calls, resume values are matched **by order**, so don't
  put them behind conditionals that can change between runs.

**Two uses in this week's graph**

| Interrupt | Trigger | Human's resume value | Effect |
|---|---|---|---|
| `clarify` | confidence < 0.6 | a category name (`"code"`) or free text | category -> route straight to that agent (trusted, no re-classify); free text -> appended to the query and the supervisor tries again |
| tool-call approval (`require_approval=True`) | right before an agent's retrieval | `True` / `False` | `False` -> the tool is never called |

Bounding the loop matters: `MAX_CLARIFICATIONS = 1`. If the human's free-text answer still
leaves the supervisor unsure, we stop asking and use the best guess. An agent that interrogates
the user three times in a row is worse than one that is occasionally wrong.

**Dynamic vs static interrupts.** `interrupt()` inside a node (dynamic, carries a payload, the
recommended style) vs `compile(interrupt_before=["node"])` (static: always pause before a named
node, no payload, mostly useful for debugging). The goal text "interrupt the graph *before* a
tool call" is met by placing `interrupt()` as the first thing in the agent node.

### 5. Worked example (the eval's two ambiguous cases)

*"Tell me about session refresh"* -- no category keywords, confidence 0.20 -> `clarify`
interrupts. Human replies `"I mean the implementation"` (free text). Query becomes
`"Tell me about session refresh\n(clarification: I mean the implementation)"`; supervisor
re-classifies, now sees "implement..." -> `code`, 0.75 -> `code_agent` runs.

*"Can we merge the function that calls the billing API?"* -- evidence split (rules: merge; code:
function, calls; domain: billing) -> 0.50 -> interrupt. Human replies `"rules"` -> routed straight
to `rules_agent`, `route.reasoning == "chosen by human"`.

## Why it matters in production

* **Specialisation scales; a monolith doesn't.** Each agent gets its own prompt, tools, index and
  eval set. Month 5 swaps the three stub retrievers for real indexes without touching the graph.
* **Routing is the first failure point.** A mis-route sends the query to the wrong index, which
  retrieves confidently irrelevant text, which the model then answers fluently. You see "bad
  answers", but the bug is upstream. Log the `Route` (category, confidence) on every request so
  you can slice quality by route.
* **Cost/latency.** The supervisor adds one LLM call to every request. Use a small fast model for
  it; if a keyword/embedding router matches it on your data, ship that.
* **Human-in-the-loop is how agents get permission to do risky things** -- sending messages,
  writing to systems, spending money. Approval-before-tool-call is the standard guardrail, and
  because the state is checkpointed, "waiting for a human" can last hours without holding a
  process open.
* **What breaks if wrong:** no checkpointer -> the graph pauses but `Command(resume=...)` raises `RuntimeError` (nothing was saved to resume from); non-idempotent code above an
  interrupt -> duplicated side effects on resume; no clarification cap -> loops; threshold never
  calibrated -> either the bot nags constantly (threshold too high) or never asks (LLM
  confidence is almost always > 0.6).

## Tradeoffs & comparisons

| Option | Strength | Weakness |
|---|---|---|
| Single agent, all tools | simplest; no routing errors | prompt/tool bloat; can't tune parts independently |
| Keyword / regex router | free, instant, deterministic, debuggable | brittle on paraphrase; confidence is crude |
| Embedding router | cheap, no LLM call, calibrated-ish margin | needs example queries per route; weak on nuance |
| **LLM supervisor (structured output)** | handles paraphrase and nuance; gives a label + confidence | extra latency/cost per request; overconfident; non-deterministic |
| Supervisor agent with sub-agents-as-tools | handles multi-specialist questions; little code | routing implicit; harder to gate on confidence |
| Handoffs / swarm | flexible, no central bottleneck | hardest to reason about and test |

Practical ladder: start with the keyword baseline (it's in this repo), measure it, and only pay
for the LLM supervisor if it beats the baseline on your labelled set.

**Tools named in the plan, and where they fit:** *LangGraph* -- the orchestration used here.
*Pydantic* (the schema layer of *Pydantic AI*) -- used for `Route`; Pydantic AI as a full agent
framework is an alternative to LangGraph, not an add-on. *LiteLLM* -- one OpenAI-style call
signature across providers; useful if the supervisor model must be swappable, not needed here.
*Vercel AI SDK* -- the TypeScript equivalent stack; relevant if the routing layer lives in a
Next.js app. *LangSmith* -- trace each run: you'll see `supervisor` -> `clarify` -> (pause) ->
agent as separate spans, with `route` in the state.

## Common pitfalls

1. **Expensive work above `interrupt()`** -- it re-runs on resume. Split into another node.
2. **Mixing `Command(goto=...)` with static edges** from the same node -- both fire.
3. **Forgetting the `Command[Literal[...]]` return annotation** -- routing still works at runtime,
   but the drawn/compiled graph is missing the node's outgoing edges (shows `node -> END` only).
4. **Different `thread_id` on resume** -- you start a new run; the paused one stays paused.
5. **Non-serialisable interrupt payloads** (objects, clients) -- send plain dicts/strings.
6. **Trusting verbalised confidence** without calibrating the threshold on labelled data.
7. **Unbounded clarification loops** -- always cap them and define the fallback.
8. **Leaking per-turn state across a long thread** -- reset `query`/`route`/`clarifications` at
   the start of each turn (`receive_query` does).
9. **Evaluating routing only on easy queries.** The informative cases are the ambiguous ones;
   score "did it ask when it should (and only then)" as well as final accuracy.
10. **Calling a 10-case eval a benchmark.** It's a smoke test.

## Check yourself

1. Why does `supervisor` return `Command(update=..., goto=...)` rather than using a conditional
   edge, and what goes wrong if you also add `add_edge("supervisor", "code_agent")`?
2. A node does `result = llm.invoke(...)` then `answer = interrupt(...)`. What happens to the LLM
   call when the human responds, and how would you restructure the graph?
3. Your supervisor reports confidence >= 0.8 on 97% of queries but is right on only 85% of them.
   What does that tell you about the 0.6 threshold, and what are two other signals you could
   gate on?
4. When would you choose sub-agents-as-tools over a classify-then-`goto` supervisor, and what do
   you give up?
5. What are the three things `interrupt()` needs to work across two separate `invoke` calls, and
   what does `Command(resume=x)` do to the value of `interrupt(...)`?
