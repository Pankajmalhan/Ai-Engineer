# Week 5 Resources

## From the roadmap paste

- **Primary**: [RAGAS documentation — Metrics section](https://ragas.io/docs)
- **Secondary**: RAGAS paper — skim the metric definitions in Section 3
- **Flagged update (Aug 2026)**: RAGAS's metric API has been restructured across
  recent versions — e.g. "Answer Relevancy" is documented differently release to
  release. Verify class names against the `latest`/`stable` docs branch, not a cached
  version. See [concept.md](concept.md)'s Common Pitfalls for the specific rename
  history this project's code works around.

## Verified current links (checked via Context7 against docs.ragas.io/en/stable)

- [RAGAS stable docs — available metrics](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/) —
  the current canonical list and definitions; this is the page to re-check against
  your installed `ragas` version before wiring up metric imports.
- [RAGAS v0.3 → v0.4 migration guide](https://docs.ragas.io/en/stable/howtos/migrations/migrate_from_v03_to_v04) —
  documents the exact API shift this week's task warns about: metrics moved from
  `ragas.metrics` to `ragas.metrics.collections`, `single_turn_ascore(sample)` became
  `ascore(**kwargs)`, and the return type changed from a plain float to a
  `MetricResult` object. Read this before touching `app/metrics.py` if RAGAS has been
  upgraded since this project was built.
- [`evaluate()` API reference](https://docs.ragas.io/en/stable/references/evaluate) —
  the current signature and parameters for the top-level `ragas.evaluate()` call used
  in `app/evaluate.py`.

## Added by Claude (not in the original paste)

- [OpenAI GPT-4o / GPT-4o-mini pricing](https://openai.com/api/pricing/) — worth
  checking before running the full 50-sample × 6-metric suite for real; this project
  defaults to `gpt-4o-mini` via `OPENAI_MODEL` to keep a full run cheap, overridable to
  match the roadmap's literal "GPT-4o" tool listing.
