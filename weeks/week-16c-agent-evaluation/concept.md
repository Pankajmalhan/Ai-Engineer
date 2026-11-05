# Week 16c -- Evaluating multi-agent systems

## Overview

Weeks 5-8 taught you to evaluate a RAG *answer*: given a question, retrieved context and a response,
score faithfulness, relevance, recall. An agent is different in kind. It makes a *sequence* of decisions
-- which specialist to hand off to, which tool to call, with what arguments, whether to keep going -- and
the final answer can look fine while the path was wasteful, lucky, or wrong in ways that will bite next
time. So you grade the **path** (the *trajectory*) as well as the destination, and because the same agent
gives different paths on different runs, you also grade **reliability**. This week you build that for the
agents you already have: the Week 14 supervisor, the Week 16b supervisor loop and the Week 16b Deep Agent.

## Core concept, in depth

### 1. Why agent evaluation is not RAG evaluation

| | RAG answer eval (Weeks 5-8) | Agent eval (this week) |
|---|---|---|
| Unit of evaluation | one (question, context, answer) | one **trajectory**: ordered tool calls, hand-offs, end state |
| What can be wrong | retrieval, grounding, relevance | wrong specialist, wrong tool, wrong arguments, wasted steps, early stop, loops, a forbidden action |
| A right answer proves... | the pipeline worked | almost nothing: it may have guessed, or taken 14 calls for a 1-call job |
| Variance | low (fixed pipeline) | high: the *model* picks the next step each time |

Langfuse's agent-eval guide groups what to measure into four dimensions, and the project covers each:

| Dimension | Question | Metric(s) used here | Deterministic? |
|---|---|---|---|
| **Tool use** | right tool, right arguments? | RAGAS `ToolCallAccuracy`, `ToolCallF1`; DeepEval `ToolCorrectness`; DeepEval `ArgumentCorrectness` | first three yes; last is LLM-judged |
| **Trajectory** | sensible plan, followed, no wasted steps? | DeepEval `PlanQuality`, `PlanAdherence`, `StepEfficiency`; project `delegation_efficiency` | DeepEval's are LLM-judged; ours is a ratio |
| **Task completion** | did the end state come out right? | DeepEval `TaskCompletion`; RAGAS `AgentGoalAccuracy`; project **end-state checks** | judged / judged / deterministic |
| **Multi-turn consistency** | does it stay coherent across turns? | not built this week (needs a user simulator; see tau-bench) | -- |

The practical rule: **use deterministic metrics wherever the ground truth is checkable, and spend LLM-judge
calls only on what cannot be checked by code** (was this plan sensible? did it reach a fuzzy goal?).

### 2. Tool-call metrics -- same trajectory, three verdicts

The Week 14 supervisor makes one tool call per query. Score it against the reference
`[search_code(k=3)]` and the three tool metrics disagree exactly where it is instructive
(these are measured values from `tests/test_tool_call_metrics.py`):

| Agent's calls | RAGAS ToolCallAccuracy | RAGAS ToolCallF1 | DeepEval ToolCorrectness |
|---|---|---|---|
| `search_code(k=3)` | 1.0 | 1.0 | 1.0 |
| `lookup_rules(k=3)` (wrong tool) | 0.0 | 0.0 | 0.0 |
| `search_code(k=3)`, then an extra `lookup_rules` | **0.0** | **0.67** | **1.0** |
| `search_code(k=5)` (wrong argument) | 0.0 | 0.0 | **1.0** |
| two-step reference, calls swapped | 0.0 | 1.0 | 1.0 (0.5 if `should_consider_ordering`) |

* **ToolCallAccuracy** is strict: the call list must equal the reference, in order. One extra call is a zero.
* **ToolCallF1** is unordered precision/recall over (name, args): a gradient, good for tracking progress.
* **DeepEval ToolCorrectness** asks "were the *expected* tools called?" -- extras are not punished, and by
  default it compares names only. It is the lenient one.

None is "right". Pick by the question: *must it be exactly this?* (Accuracy) *how close is it?* (F1)
*did it at least do the necessary things?* (ToolCorrectness). Two more details that bite:

* **Free-text arguments.** RAGAS scores a reference call's arguments one by one (1 of 2 matching = 0.5).
  A reference that pins a search `query` therefore marks down any good paraphrase. The project drops
  free-text args before comparing and leaves "was the query any good?" to the LLM-judged `ArgumentCorrectness`.
* **ToolCorrectness is deterministic but its constructor still wants a judge.** The project passes a
  `NoJudge` that raises if called -- so a passing score is *proof* no LLM was involved.

### 3. Multi-agent-specific: handoff accuracy

In a supervisor design the most consequential decision is **who gets the work**. Formalise it:
`handoff accuracy = correct specialist / total queries`, over a *labelled* set -- but report more than one number:

* a **confusion matrix** (rows expected, columns routed) and **per-label recall** -- accuracy hides *which* way it errs;
* **subsets** -- the Week 14 queries vs fresh ones, to expose overfitting;
* **first-pass accuracy** (the supervisor's own guess before any human clarification) and
  **asked-when-ambiguous** (did it ask exactly when it should?).

Worked through on the real recorded run of the Week 14 supervisor with its keyword classifier
(30 queries: 10 Week 14's own + 20 written fresh):

```
handoff accuracy 77% (23/30)        first-pass 70% | asked-when-ambiguous 70%
recall: code 70%, rules 60%, domain 100%
by subset: w14 100%, new 65%
                  code  domain   rules
   expected code     7       3       0
   expected rules    1       3       6
   expected domain   0      10       0
```

Read it like a diagnostic, not a score. (a) **10/10 became 13/20**: Week 14's ad hoc check was flattering,
exactly as its README warned -- the keyword lists were written by the same person as the ten queries.
(b) **Domain recall 100% but 16 queries land there for 10 true ones**: when the classifier has no signal
it falls back to `domain`, so every low-confidence miss goes the same way. A single accuracy number cannot
show that; a confusion matrix does in one glance. (c) This is a **keyword baseline** -- the number an LLM
classifier has to beat to justify its latency and cost.

Because the single-hop supervisor calls exactly one retriever, the tool called is a pure function of the
route -- so RAGAS ToolCallAccuracy, ToolCallF1 and DeepEval ToolCorrectness all come out at 0.767, the same
as handoff accuracy. Three independent implementations agreeing is a useful sanity check of the pipeline.

### 4. Orchestration overhead and step efficiency

"Which architecture would I run?" is a cost question as much as a quality one. Two lenses:

* **Delegation efficiency** = `distinct sources a task needs / delegations actually made`, capped at 1. A
  one-source question answered by three sub-agents scores 0.33. It measures *wasted hops*, and it is
  architecture-neutral (a supervisor "hop" and a Deep Agent `task` call are both a delegation).
* **Raw cost**: LLM calls and tokens, **including nested ones**. A callback passed in the run config sees
  inside sub-agents; the lead agent's message thread does not. The recorded offline Deep Agent run shows
  14 model calls and 10 tool calls where the lead's thread contains only `write_todos`, three `task`s and
  `write_file`.

DeepEval's `StepEfficiencyMetric` is the *judged* version: an LLM reads the trace and rates whether steps
were necessary. Use the ratio as the cheap always-on number and the judge for a periodic check.

### 5. Success defined by end state (tau-bench)

tau-bench (Sierra) grades an agent by **where it leaves the world**, not by its transcript. From the
tau2-bench evaluation docs: a task's reward is computed from components -- `DB` compares the final
environment state to a target and "any trajectory that reaches an equivalent state passes"; `COMMUNICATE`
checks required information was conveyed; the final reward is the **product** of the components; and the
action-by-action `ACTION` check is meant only for tasks whose listed actions are the sole acceptable path.
Its `partial_action_reward` is documented as similarity to *one* reference path, "not correctness".

The project borrows the format: a task = **user goal + required end state**, where the "world" is the run's
footprint -- report text, saved files, tool calls and their arguments, delegations. Checks are declarative
(`report_matches`, `report_not_matches`, `file_written`, `tool_called`, `tool_args_not_matching`,
`delegated_to`, `max_tool_calls`...), and the five `hard_5.json` tasks are chosen to probe things a
transcript-reading judge is bad at:

| Task | What it probes |
|---|---|
| h1 | **precision**: list only the rules actually violated (a model that lists every rule fails) |
| h2 | **synthesis** across code + rules + policy into concrete changes |
| h3 | **partial compliance**: one part implemented, one missing, answered part by part |
| h4 | **abstention**: a question the docs don't answer; inventing "90 days" must fail |
| h5 | **constraint following**: right answer but opened a forbidden file = fail |

A lesson from building them: **your own checks can be wrong.** The first draft required the regex `12 hours`;
a correct answer saying "12-hour" or "12 hour" failed. Tests that feed each task a good answer, a
plausible-wrong answer, and phrasing variants caught it. Treat every end-state check as code under test.

### 6. Reliability: pass^k

Run each task `n` times. `pass@1` is the average success rate. `pass^k` is the probability that **all k**
trials of a task succeed; with `c` successes in `n` trials the unbiased estimate is `C(c,k)/C(n,k)`,
averaged over tasks. An agent that succeeds 75% of the time (3 of 4) has `pass^1=0.75`, `pass^2=0.50`,
`pass^3=0.25`, `pass^4=0`. If your users run the same task daily, `pass^k` is the number they feel -- and
it can only fall as `k` rises. (The pass^k definition is the tau-bench paper's, cited from memory; the
tau2-bench pages fetched this week do not define it.)

### 7. LLM-judged metrics and the CI pattern

DeepEval's `TaskCompletion`, `StepEfficiency`, `PlanQuality` and `PlanAdherence` are **trajectory metrics**:
documented against a *trace* produced by `@observe`-instrumented code. (The installed 4.3.1 also accepts a plain
`LLMTestCase` -- tested -- but then has only the `tools_called` list to go on.) To gate a recorded run in CI
without re-running the agent, the project **replays** it: an agent span with one named tool span per recorded
call, and the trace's input / output / `tools_called` set, so the metrics see the shape they would on a live
run. Sub-agent nesting is flattened -- the metrics see the order of calls, not who made them. Then the Week 6
pattern applies unchanged: `assert_test(golden=..., metrics=[...])` with a threshold per metric.

The CI shape the project uses:

1. **Record** (`scripts/record.py`) -- run the real agent through a bridge, write JSONL trajectories.
2. **Replay** (`scripts/evaluate.py`, pytest) -- score the recordings; fast, diffable, no agent run.
3. **Gate** -- deterministic floors always on (handoff accuracy, `ToolCallF1`, end-state checks); judged
   floors only with a key and real recordings. Thresholds are set *just under the current baseline* so the
   gate passes today and trips on regression; raise them as the agent improves.

LLM judges are noisy and have their own biases, so gate judged metrics with generous floors, and calibrate
them against the deterministic metrics rather than trusting them alone.

## Why it matters in production

* **"It gave the right answer" is not an acceptance test for an agent.** The path decides cost, latency,
  safety (did it call a tool it should not?) and reliability.
* **Regressions in agents are silent.** A prompt tweak can move 10% of queries to the wrong specialist
  while the demo still works. Handoff accuracy and tool-call F1 on a fixed labelled set turn that into a red build.
* **Orchestration is a cost centre.** Every extra delegation re-sends context. Counting nested calls is
  how you find that "the clever architecture" costs 14 model calls where 1 would do.
* **Non-determinism means one run proves little.** Reliability (`pass^k`) is what an on-call engineer inherits.

## Tradeoffs & comparisons

| Choice | Wins when | Costs |
|---|---|---|
| Deterministic metrics (tool-call, handoff, end-state) | ground truth is checkable; you want a CI gate | only as good as the checks; blind to fuzzy quality |
| LLM-judged metrics (TaskCompletion, PlanQuality...) | the goal or plan is fuzzy | money, latency, judge variance and bias |
| End-state grading | many valid paths | needs a well-defined, checkable end state |
| Reference-trajectory grading (`ACTION`, ToolCallAccuracy) | exactly one acceptable path | punishes valid alternative paths |
| Recorded/replayed evaluation | CI, regression gating, cheap iteration | stale if the agent changes and nobody re-records |
| Live evaluation | measuring a change's real effect | slow, costly, noisy |

## Common pitfalls

* **Grading the transcript instead of the end state** -- and rewarding the wrong path or punishing a valid one.
* **One accuracy number.** Without a confusion matrix and subsets you miss the systematic bias and the overfit.
* **Testing on the queries you built the agent with** (Week 14's 10/10).
* **Treating metrics with similar names as the same.** ToolCorrectness 1.0 and ToolCallAccuracy 0.0 can describe one run.
* **Free-text arguments in strict matching.**
* **Counting only the lead agent's calls.** Sub-agent work is invisible in its thread.
* **Brittle regex end-state checks** (singular/plural, hyphens). Test the checks with good, bad and variant answers.
* **A single trial.** Report `pass^k`, not just success.
* **Gating on judged metrics with tight thresholds.** Noise will flake your build.
* **Comparing architectures on one task.** The difference depends on how many sources a task needs.

## Check yourself

1. An agent makes one extra, harmless tool call. What do RAGAS `ToolCallAccuracy`, `ToolCallF1` and DeepEval
   `ToolCorrectness` each return for a reference of one call, and which would you gate a merge on?
2. The Week 14 keyword supervisor scored 10/10 on its own queries and 13/20 on fresh ones. What does the
   confusion matrix add that the accuracy does not? What would you check next?
3. A one-source question is answered via three delegations. What is the delegation efficiency, and why isn't
   it a complete measure of cost?
4. An agent solves a task in 3 of 4 trials. Give `pass^1`, `pass^2`, `pass^4`. Why does `pass^k` fall with `k`?
5. DeepEval's trajectory metrics are documented against live `@observe` traces. How does the project gate a
   *recorded* run with them, and what information does that replay lose compared with a live trace?
