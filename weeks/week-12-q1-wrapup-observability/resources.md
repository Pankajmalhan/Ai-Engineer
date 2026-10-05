# Week 12 resources

## Given

- Primary: Langfuse "Monitoring" documentation (no URL was supplied in the paste; the pages
  this week's work actually relied on are listed below)
- Secondary: study how Anthropic and Weaviate write technical blog posts -- problem-first,
  then solution (no specific posts were named)

## Added by Claude (the pages the build was checked against)

Langfuse -- checked while building, because the roadmap's "email on error rate > 2%" turned
out not to match what Langfuse alerts can do:

- Alerts (data sources, metrics, thresholds, severity states, Slack / Webhook / GitHub Actions
  channels -- **no e-mail channel**): https://langfuse.com/docs/observability/features/alerts
- Webhook signature verification (`x-langfuse-signature: t=<ts>,v1=<hex>`, HMAC-SHA256 over
  `<ts>.<raw body>`): https://langfuse.com/docs/prompt-management/features/webhooks-slack-integrations
- Metrics API v2 (`/api/public/v2/metrics`; views `observations`, `scores-numeric`,
  `scores-categorical`, `scores-boolean`): https://langfuse.com/docs/metrics/features/metrics-api
- Langfuse on OpenTelemetry (OTLP endpoint `/api/public/otel`, GenAI semantic conventions):
  https://langfuse.com/integrations/native/opentelemetry
- Langfuse Python SDK source and reference (the typed `api.scores.get_many` client this week's
  poller uses): https://github.com/langfuse/langfuse-python

OpenTelemetry:

- GenAI semantic conventions (`gen_ai.*` attributes; still marked experimental):
  https://opentelemetry.io/docs/specs/semconv/gen-ai/

Technical writing (suggested exemplars for the "problem first" structure -- verify the URLs
still resolve, these were chosen from memory, not fetched):

- Anthropic, "Building effective agents": https://www.anthropic.com/research/building-effective-agents
- Weaviate, "Hybrid search explained": https://weaviate.io/blog/hybrid-search-explained
