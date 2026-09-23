# Resources

## From the roadmap paste

- **Primary** -- Langfuse self-hosting guide. **Updated per the paste's own flagged
  note**: Langfuse shipped a major v4 release on 2026-08-17 with self-hosting
  architecture changes, so the primary link here points at the v3->v4 migration guide
  rather than the general (now-dated) self-hosting page:
  - https://langfuse.com/self-hosting/upgrade/upgrade-guides/upgrade-v3-to-v4
  - (general self-hosting/docker-compose reference, still useful alongside the
    migration guide): https://langfuse.com/self-hosting/deployment/docker-compose
- **Secondary** -- Braintrust "Evals as CI" guide:
  https://www.braintrust.dev/docs/evaluate/run-in-ci
- Langfuse v4 changelog (as supplied in the paste)
- "Top LLM Observability & Eval Platforms in 2026" comparison (as supplied in the paste)

## Tools named in the paste

- Braintrust -- https://www.braintrust.dev/docs
- Langfuse -- https://langfuse.com/docs
- OTel GenAI semantic conventions (Langfuse's Python SDK v3+ tracing is OTel-based
  under the hood) -- https://opentelemetry.io/docs/specs/semconv/gen-ai/
- LangSmith -- https://docs.smith.langchain.com/
- Arize Phoenix -- https://arize.com/docs/phoenix (named as a tool this week, not used
  directly in project/ -- see concept.md's comparison table for where it would fit
  relative to Braintrust/LangSmith/Langfuse if you want to look further)
- Docker / Docker Compose -- https://docs.docker.com/compose/

## Added by Claude (not in the original paste)

- Braintrust Python SDK API reference (used to get `Eval()`, `init_dataset()`, and
  `Dataset.insert()`/`.flush()` signatures right rather than guessed):
  https://www.braintrust.dev/docs/sdks/python/api-reference
- Langfuse Python SDK token/cost tracking docs (used for `app/tracing.py`'s
  `usage_details`/`cost_details` shape):
  https://langfuse.com/docs/observability/features/token-and-cost-tracking
