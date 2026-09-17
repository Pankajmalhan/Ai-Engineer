# Resources

## From the roadmap

- **Primary**: [DeepEval documentation](https://docs.confident-ai.com) — "Getting Started" and "Metrics" sections
- **Secondary**: [DeepEval GitHub README](https://github.com/confident-ai/deepeval)
- **Note (✓ verified Aug 2026)**: DeepEval's red-teaming functionality has been split out
  into a companion package, [DeepTeam](https://github.com/confident-ai/deepteam) —
  relevant alongside Week 7.
- [DeepEval — Unit Testing in CI/CD](https://docs.confident-ai.com/docs/evaluation-unit-testing-in-ci-cd)

## Added by Claude, while implementing this week

Pulled live via Context7 (docs.confident-ai.com / the deepeval GitHub repo) rather than
from training data, since DeepEval's API has moved before:

- [Evaluation introduction — `assert_test` + pytest](https://github.com/confident-ai/deepeval/blob/main/docs/content/docs/evaluation-introduction.mdx)
- [`LLMTestCase` reference](https://github.com/confident-ai/deepeval/blob/main/docs/content/docs/(concepts)/(test-cases)/evaluation-test-cases.mdx)
- [FaithfulnessMetric](https://github.com/confident-ai/deepeval/blob/main/docs/content/docs/(rag)/metrics-faithfulness.mdx),
  [AnswerRelevancyMetric](https://github.com/confident-ai/deepeval/blob/main/docs/content/docs/(rag)/metrics-answer-relevancy.mdx),
  [ContextualRecallMetric](https://github.com/confident-ai/deepeval/blob/main/docs/content/docs/(rag)/metrics-contextual-recall.mdx)
- [Unit testing in CI/CD](https://docs.confident-ai.com/docs/evaluation-unit-testing-in-ci-cd) — GitHub Actions workflow examples
- [Data privacy / `DEEPEVAL_TELEMETRY_OPT_OUT`](https://github.com/confident-ai/deepeval/blob/main/docs/content/docs/data-privacy.mdx) —
  confirms DeepEval runs fully locally/keyless; a `CONFIDENT_API_KEY` is only needed to
  upload results to the Confident AI dashboard, not to gate CI
- [`astral-sh/setup-uv` GitHub Action](https://github.com/astral-sh/setup-uv) — used in
  this week's `.github/workflows/` file to install `uv` in CI
