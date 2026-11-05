# Decision: which parts of the assistant get a harness, which stay plain LangGraph

**Status: PROVISIONAL.** Everything under "measured" is structural and test-backed. Everything about
quality, cost and latency is a **hypothesis** until `uv run python -m app.compare` is run with a real model
(none was available when this was built). Fill in the table below, then confirm or flip the decision.

## Provisional decision

**Keep the Week 14 LangGraph supervisor as the assistant's front door. Add a Deep Agent only behind it,
as a tool the supervisor can call for open-ended, multi-step investigations** (audits, "why did X
regress", migration plans).

| Part of the assistant | Choice | Why |
|---|---|---|
| Classify the question, pick code / rules / domain index, return top hits | **Plain LangGraph** | One hop, shape known in advance, cost bounded, `interrupt()` clarification already built (Week 14). A harness adds plan + delegation turns it doesn't need. |
| Conversation memory, human approval gates | **Plain LangGraph** | Native checkpointing and `interrupt()`; Week 20b's persistent memory plugs in here. |
| "Audit / investigate / write up" tasks needing several sources and a deliverable | **Deep Agent** | Shape depends on what it finds; sub-agent isolation keeps raw evidence out of the thread; a file is a natural deliverable. |
| Anything that executes code | **Neither yet** | Needs the Week 18c sandbox and Week 23c agent guardrails first. Do not enable `execute`/`FilesystemBackend`. |

## What the project measured (structural; no model involved)

| Fact | Evidence |
|---|---|
| The audit needs all three sources; none alone covers more than half of it | `test_no_single_source_can_answer_the_whole_task_but_the_union_can` |
| Week 14's route-once pattern cannot complete it (1/6 facts) | `test_one_hop_reproduces_week_14_...`, `test_the_loop_gets_the_full_score_and_one_hop_cannot` |
| The minimal fix is a loop + a hop cap; without the cap a non-terminating planner runs until the recursion limit | `test_a_planner_that_never_finishes_is_stopped_by_the_hop_cap`; mutation check: removing the cap fails the suite |
| The supervisor loop puts every specialist's raw output (including a whole opened file) into one shared thread the writer re-reads | `test_all_gathered_evidence_is_in_the_one_shared_thread_the_writer_sees` |
| In the Deep Agent the raw file body is in the sub-agent's context and **not** in the lead's thread; only the summary crosses | `test_subagent_raw_output_is_isolated_from_the_parent_thread` |
| Sub-agents don't see siblings' work or the lead's plan | `test_subagents_cannot_see_each_others_work_or_the_parents_plan` |
| `write_todos` is opt-in (`TodoListMiddleware`), contrary to the roadmap text | `test_write_todos_is_opt_in_not_a_default` |
| Offline, one audit costs **14** model calls in the Deep Agent (6 lead + 8 sub-agent) vs 1 writer call + N planner calls in the supervisor | `test_run_deep_scores_the_saved_report_and_counts_every_call` |
| Deep Agent failure modes are visible: report never saved; runaway turns | `test_a_report_given_in_chat_but_never_saved_is_flagged`, `test_a_runaway_agent_is_reported_as_an_error_not_a_crash` |

## What is NOT known (needs the real run)

Fill in after `uv run python -m app.compare` (repeat 3-5 times; agent runs vary):

| | supervisor, 1 hop | supervisor, loop | deep agent |
|---|---|---|---|
| facts found (of 6), median | _run it_ | _run it_ | _run it_ |
| LLM calls | _run it_ | _run it_ | _run it_ |
| total tokens | _run it_ | _run it_ | _run it_ |
| lead/parent thread chars | _run it_ | _run it_ | _run it_ |
| wall-clock seconds | _run it_ | _run it_ | _run it_ |
| failure modes seen (read the reports) | _run it_ | _run it_ | _run it_ |

Open questions the run should answer:

* Does the Deep Agent's extra call count (plan + 3 delegations + sub-agent turns) cost more than the
  supervisor loop on a corpus this small? **Expect yes**; the harness's context savings need a large corpus.
* Does the lead write `/audit.md`, or answer in chat? How often does it skip a sub-agent?
* Does the LLM supervisor `finish` too early (a recall miss) or repeat a specialist?
* Does a weak sub-agent summary drop a fact the lead cannot recover (lossy hand-off)?

## Revisit the decision if

* The real run shows the supervisor loop matching the Deep Agent on facts **and** costing clearly less
  at realistic corpus size -- then keep everything in LangGraph and build the one extra loop by hand.
* The Deep Agent's variance is high (it skips steps or fails to save the report on a meaningful share of
  runs) -- then constrain it (`interrupt_on`, a stricter prompt, a `response_format`) or keep it out of the
  user-facing path.
* The assistant's tasks start routinely exceeding the context window (large repos) -- then the harness's
  offloading and summarisation become the deciding factor, and this toy corpus under-states them.
* Rerun on a corpus large enough to cross the 20,000-token offload threshold; that is the experiment this
  project cannot do.
