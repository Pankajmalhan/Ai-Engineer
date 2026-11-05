---
name: week-plan
description: Scaffold or update a week in the AI-engineer learning roadmap from just a week number — fetches the latest published "AI Engineer Roadmap" artifact, pulls that week's goals/tasks/resources, then writes a concept.md theory explainer, resources.md, notes.md, and a tested project/ when the goal calls for implementation. Trigger on "/week-plan 17", "let's start week N", "plan week 16b", or a pasted roadmap block (fallback).
argument-hint: <week number, e.g. 17 or 16b>
---

# Week Plan

Takes a week number (e.g. `17`, `16b`, `6b.1`), reads that week's goals / tasks /
resources from the published roadmap artifact, and scaffolds a folder under `weeks/` so
the user can learn the concept and, when relevant, build and run real code for it.

The user will normally give **only the week number**. Do not ask them to paste the
description — the artifact is the source of truth. A pasted block is still accepted as a
fallback (see step 2).

## 1. Fetch the latest roadmap (every time)

The roadmap is edited over time (links get updated, weeks get added), so always fetch
it fresh — never reuse a saved copy from an earlier session.

1. Call the Artifact tool: `action: "read"`, `url: https://claude.ai/artifact/37FwVAbsCcqyYGkNCvvyzi`.
   The result header names the saved HTML file path
   (`.../tool-results/artifact-....html`). The inline preview is truncated; use the file.
2. Extract the week:
   `python3 -I .claude/skills/week-plan/scripts/extract_week.py <saved-html-path> <week>`
   Prints JSON: `quarter`, `month` (theme + blurb), and `week` with `title`, `goals`,
   `tasks`, `tools`, `primary`, `secondary`, `status` (`current` | `update` | `fix`),
   `note`, `alts` (`[title, url]` pairs).
   `--list` instead of a week shows every week id and title.
3. If the week isn't found, the script lists the valid ids — show them and ask which one.
   If the Artifact read fails (not signed in, URL gone), say so plainly and fall back to
   a pasted block rather than guessing the week's content.

## 2. Figure out the target directory

- Week id → directory number: `17` → `week-17-…`, `16b` → `week-16b-…`, `6b.1` → `week-6b1-…`.
- Derive a 2-4 word kebab-case topic slug from the week `title`
  (e.g. "Tree-sitter AST parsing for the code index" → `tree-sitter-ast-parsing`).
- Target: `weeks/week-<id>-<slug>/`. If a directory for that id already exists (match on
  the `week-<id>-` prefix), this is an UPDATE — see step 7.
- If no week number was given and the user pasted a block instead: use an explicit week
  number from the paste, else `max existing + 1`, and parse goal/task/resources loosely
  from the prose. Don't invent missing sections; leave placeholders.

## 2b. Use what the artifact gives you

- `goals` and `tasks` are the spec. Build to them, don't reinterpret them.
- `note` / `status`: when `status` is `update` or `fix`, the note says the original
  tool/link is outdated or renamed. Follow the note (e.g. use the successor library,
  the renamed product) and call it out in `concept.md` so the user knows why the plan
  text and the project differ. Use `context7` for current library docs when the week
  names a library/SDK, since these tools change fast.
- `primary`, `secondary`, and `alts` go into `resources.md` (alts are the refreshed
  links — mark them as such). `primary`/`secondary` are titles without URLs; don't
  fabricate URLs for them.
- `month.theme`/`blurb` give the surrounding context; use it so the week's concept
  connects to what the quarter is building toward.

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
