---
name: week-plan
description: Scaffold or update a week in the AI-engineer learning roadmap from a pasted goal/task/resources block — writes a concept.md theory explainer, captures resources.md, sets up notes.md, and builds a tested project/ when the goal calls for implementation. Trigger on "/week-plan", "let's start week N", "here's this week's goal", or any pasted roadmap block naming a weekly goal, task, and resources.
---

# Week Plan

Turns a raw pasted roadmap block (goal + weekly task + learning resources, in whatever
shape the user pastes it — this is often rough voice-to-text style prose, not a form)
into a scaffolded folder under `weeks/`, so the user can learn the concept and, when
relevant, build and run real code for it.

## 1. Figure out which week this is

- List existing `weeks/week-NN-*` directories. If the user's paste names a week number
  explicitly (e.g. "Week 3", "week3"), use that. Otherwise use `max existing + 1`
  (or `01` if `weeks/` doesn't exist yet).
- Derive a short kebab-case topic slug from the goal (e.g. "single-vector retrieval
  limitations in production, implement BM25 sparse retrieval" → `sparse-retrieval-bm25`).
  Keep it to 2-4 words.
- Target directory: `weeks/week-NN-topic-slug/`. If a directory for this week number
  already exists, this is an UPDATE, not a fresh scaffold — see step 7.

## 2. Parse the pasted block

Read it loosely and pull out:
- **Goal(s)** — what the user should understand or be able to do by the end of the week
- **Task(s)** — the concrete thing(s) to implement/do
- **Resources** — any links, papers, docs, videos listed

If a section is genuinely missing (e.g. no resources given), don't invent one — leave
a placeholder in `resources.md` rather than fabricating links. Ask the user a
clarifying question only if the goal is too vague to act on at all; otherwise use
reasonable judgment and proceed.

## 3. Decide: theory only, hands-on, or both

Hands-on if the task uses words like implement/build/write/code/benchmark/train, or
names a concrete artifact (e.g. "implement BM25 sparse retrieval"). Theory-only if the
task is about understanding/comparing/explaining a concept with no artifact named. Most
weeks are both — explain the concept, then build the thing that demonstrates it.

## 4. Write `concept.md`

This is the core deliverable — it has to actually teach, not summarize. Structure:

- **Overview** — one paragraph, plain language: what this concept is and why it exists
- **Core concept, in depth** — the real mechanics: definitions, how it works, math/
  algorithms where relevant, worked through with a concrete example tied to the user's
  specific task
- **Why it matters in production** — where this shows up in real systems, at what
  scale, what breaks if you get it wrong
- **Tradeoffs & comparisons** — how it stacks up against the alternative(s) it's
  usually compared to (e.g. BM25 vs. dense/single-vector retrieval, when each wins)
- **Common pitfalls**
- **Check yourself** — 3-5 questions the user should be able to answer after reading

Tailor every section to the specific goal text. Do not produce generic "what is RAG"
filler if the goal is narrower than that — write to the exact concept named.

## 5. Write `resources.md` and `notes.md`

- `resources.md` — the resources pulled from the paste, plus (only if the set given is
  thin or empty) 1-2 well-known primary sources for the concept, clearly marked as
  suggestions added by Claude vs. what the user supplied.
- `notes.md` — a blank template with headers `## Questions`, `## Key takeaways`,
  `## Open threads`. Content under these headers is the user's — don't pre-fill it.

## 6. If hands-on: scaffold and RUN a real project

Under `weeks/week-NN-topic-slug/project/`:

- Python by default (`uv` if available — check with `which uv`; otherwise venv + pip),
  `pytest` for tests.
- Implement the actual task named in the goal — not a stub. Write tests that exercise
  it meaningfully (real inputs/outputs, not just "it doesn't crash").
- Run the tests and the code before declaring the week done. If something doesn't
  work, fix it — don't hand back a broken scaffold.
- `project/README.md` — what it does, how to install deps, how to run it, how to run
  tests.

## 7. Updating an existing week

If `weeks/week-NN-*` already exists: never overwrite `notes.md` — it's the user's.
Append to `resources.md` rather than replacing it. Extend `concept.md`/`project/`
based on what the new paste asks for; read the existing project code first and extend
it in place rather than regenerating from scratch.

## 8. Report back

Summarize what was created/changed in one short paragraph, with paths. If a project
was built, state that tests were run and passed (or what's still failing and why).
