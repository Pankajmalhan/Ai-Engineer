# AI Engineer Learning Roadmap

Personal learning repo for becoming an AI engineer, organized around a weekly roadmap
(goals → weekly tasks → resources). Each week gets its own folder with a theory
explainer and, when the week calls for it, a working, tested code project.

## Structure

```
weeks/
  week-01-<topic-slug>/
    concept.md     theory explainer for the week's concept(s)
    resources.md   learning resources for the week
    notes.md       your own running notes
    project/       (only when the week has a hands-on task) runnable, tested code
```

## How to add a week

Run the `week-plan` skill with just the week number: `/week-plan 17` (or `16b`, `6b.1`).
It reads the latest published
[AI Engineer Roadmap artifact](https://claude.ai/artifact/37FwVAbsCcqyYGkNCvvyzi) each
time, so edits to the roadmap are always picked up, then:

1. Pulls that week's goals, tasks, tools and resources (including refreshed links)
2. Writes `concept.md` explaining the concept(s), tailored to the week's goal
3. Captures resources in `resources.md` and sets up a blank `notes.md`
4. If the task calls for implementation, scaffolds a Python project under `project/`,
   implements it, and runs the tests before calling it done

Re-running a week that already exists updates it in place instead of starting over.
Pasting a roadmap block still works as a fallback.

## Defaults

- Hands-on project weeks default to Python (`uv` if available, otherwise venv + pip)
  with `pytest` for tests.
# Ai-Engineer
