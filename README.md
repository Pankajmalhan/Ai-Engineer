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

Paste your goal / weekly task / learning resources for the week — in whatever shape
your plan has them — and run the `week-plan` skill (`/week-plan`). It will:

1. Figure out the week number and a topic slug
2. Write `concept.md` explaining the concept(s), tailored to your specific goal
3. Capture your resources in `resources.md` and set up a blank `notes.md`
4. If the task calls for implementation, scaffold a Python project under `project/`,
   implement it, and run the tests before calling it done

Come back to a week any time — pasting more for a week that already exists updates it
in place instead of starting over.

## Defaults

- Hands-on project weeks default to Python (`uv` if available, otherwise venv + pip)
  with `pytest` for tests.
# Ai-Engineer
