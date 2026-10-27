# Week 15 resources

## Given

- Primary: Vercel AI SDK documentation -- "Getting Started" and "Streaming" sections (sdk.vercel.ai)
- Secondary: "Tool Use" section of the same docs
- Update (Aug 2026): AI SDK versions 5, 6 and 7 shipped since the plan was written, with breaking
  changes to streaming/tool-call APIs across majors. Build against the live docs, not a pinned version.
  - AI SDK 7 announcement -- Vercel blog (no URL supplied; find it on vercel.com/blog)
  - ai-sdk.dev -- current docs: https://ai-sdk.dev (the old sdk.vercel.ai domain was replaced by this one)

## Added by Claude

Pages this build was checked against (ai-sdk.dev, via Context7; verified against `ai@7.0.137` type
definitions after install):

- Migration guide to AI SDK 7 (`isStepCount`, `finalStep`, `activeTools`): https://ai-sdk.dev/docs/migration-guides/migration-guide-7-0
- Migration guide to AI SDK 5 (UI message stream, `stopWhen`): https://ai-sdk.dev/docs/migration-guides/migration-guide-5-0
- `createUIMessageStream` reference (writer API, `text-start` / `text-delta` / `text-end`): https://ai-sdk.dev/docs/reference/ai-sdk-ui/create-ui-message-stream
- `createUIMessageStreamResponse` reference: https://ai-sdk.dev/docs/reference/ai-sdk-ui/create-ui-message-stream-response
- Hono cookbook (streaming from a non-Next server): https://ai-sdk.dev/cookbook/api-servers/hono
- Provider management (`wrapLanguageModel`, registries, `createOpenAICompatible`): https://ai-sdk.dev/docs/ai-sdk-core/provider-management
- OpenAI-compatible providers (how LiteLLM plugs in): https://ai-sdk.dev/providers/openai-compatible-providers
- Testing (`MockLanguageModelV4`, `simulateReadableStream`): https://ai-sdk.dev/docs/ai-sdk-core/testing
- AI Gateway provider (built-in `models` fallback option, an alternative to our middleware): https://ai-sdk.dev/providers/ai-sdk-providers/ai-gateway

Not looked up this week, so not linked: LiteLLM's own docs (proxy `fallbacks` config) and LangGraph's
streaming docs. Add them here if you extend the fallback or the Python streaming.

### Added with the browser UI (client-side tools)

- Chatbot tool usage -- `useChat`, `onToolCall`, `addToolOutput`, `sendAutomaticallyWhen`: https://ai-sdk.dev/docs/ai-sdk-ui/chatbot-tool-usage
- Troubleshooting: tool invocation missing result (why not to `await` inside `onToolCall`): https://ai-sdk.dev/docs/troubleshooting/tool-invocation-missing-result
- Human-in-the-loop cookbook (tool approval before a sensitive tool runs): https://ai-sdk.dev/cookbook/next/human-in-the-loop

### Provider note

- The plan names Claude Sonnet as primary. This build uses OpenAI instead (no Anthropic key available): `@ai-sdk/openai` provider page -- https://ai-sdk.dev/providers/ai-sdk-providers/openai
