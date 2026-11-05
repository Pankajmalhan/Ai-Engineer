# Decision: which architecture would I run in production -- supervisor loop or Deep Agent?

**Status: NOT YET DECIDABLE.** The comparison needs a real model, and none was available. What *can* be
written now, honestly, is the decision procedure -- fixed **before** seeing data so the result cannot be
rationalised after the fact -- plus what the offline work already established.

## Carried forward (Week 16b's provisional decision)

Keep the Week 14 supervisor as the front door for single-hop routing; use a Deep Agent only for open-ended,
multi-step investigations. This week's job is to confirm or overturn that with measurements.

## Decision rules (set in advance)

Run `scripts/record.py w16b --trials 3` (10 tasks x 2 architectures x 3 trials), then
`scripts/evaluate.py compare --runs data/runs/w16b_tasks_10.jsonl`.

1. **Quality first.** Prefer the architecture with the higher **success rate on 3-source tasks** (t08-t10), where the
   task genuinely needs several sources. A difference under ~10 percentage points on 9 runs per cell is noise;
   do not decide on it.
2. **Then reliability.** Compare `pass^3`. If one architecture's `pass^3` is more than 0.15 lower despite a similar
   `pass^1`, it is the flakier one -- penalise it.
3. **Then cost, per source count.** Use LLM calls and tokens **per success**, not per run. If the Deep Agent is not
   clearly ahead on 3-source tasks it should not be the default, because it will cost more on 1-source tasks.
4. **Efficiency sanity.** Delegation efficiency below ~0.5 on 1-source tasks means the architecture over-delegates;
   that is a prompt/design bug to fix before comparing further.
5. **Then the hard tasks.** Run `hard_5` with 4 trials. An architecture that fails h4 (invents a retention period) or
   h5 (opens forbidden files) is unfit for user-facing use regardless of its other numbers.
6. **Tie-break:** the simpler, cheaper, more predictable one -- the supervisor loop.

## What is established already (no model needed)

| Fact | Where |
|---|---|
| Single-hop routing cannot answer a 3-source task; a loop is the minimum fix | Week 16b tests (1/6 vs 6/6 facts, scripted) |
| The Week 14 baseline routes 77% correctly, 100% on its own queries but 65% on fresh ones; it falls back to `domain` when unsure | `data/runs/w14_heuristic.jsonl`, `test_routing_recorded.py` |
| Nested sub-agent tool calls are invisible in the lead's thread but captured in the recorded trajectory (10 calls, 14 model calls for one audit) | `test_the_deep_agent_trajectory_exposes_nested_calls...` |
| The 15 task definitions accept correct answers (including rephrasings) and reject plausible wrong ones | `tests/test_end_state.py` |

## Results to fill in

| | supervisor loop | deep agent |
|---|---|---|
| success rate, all 10 tasks | _run it_ | _run it_ |
| success rate, 3-source tasks | _run it_ | _run it_ |
| pass^1 / pass^2 / pass^3 | _run it_ | _run it_ |
| delegation efficiency | _run it_ | _run it_ |
| LLM calls / tokens per success | _run it_ | _run it_ |
| hard_5 pass^4 (h1-h5) | _run it_ | _run it_ |
| DeepEval StepEfficiency / TaskCompletion (judged) | _run it_ | _run it_ |

**Decision:** _pending the run_

## Revisit if

* The LLM classifier replaces the keyword baseline for Week 14 -- re-record, re-set the gate thresholds.
* The corpus grows past the harness's offload / summarisation thresholds -- the comparison changes (see Week 16b).
* The judged metrics disagree with the end-state checks on many runs -- then the checks or the judge need fixing first.
