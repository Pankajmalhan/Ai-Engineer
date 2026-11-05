# Week 13 resources

## Given

- Primary: LangGraph documentation -- "Quickstart: Build a Chatbot" tutorial
- Secondary: LangGraph GitHub -- `examples/memory-chatbot`
- Update (Aug 2026): LangGraph's docs moved from the old GitHub Pages site to the unified
  docs.langchain.com. LangChain also shipped a higher-level **Deep Agents** framework on top of
  LangGraph in 2026 -- an emerging pattern, not a replacement for these fundamentals.
  - Persistence -- Docs by LangChain (current site): https://docs.langchain.com/oss/python/langgraph/persistence
  - LangGraph.js -- Build a Chatbot (no direct URL was supplied; find it under docs.langchain.com/oss/javascript/langgraph)

## Added by Claude

Pages the build was checked against (docs.langchain.com, via Context7):

- Checkpointers (`InMemorySaver`, `thread_id`, checkpoint per super-step): https://docs.langchain.com/oss/python/langgraph/checkpointers
- Observability with LangSmith (`LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, `tracing_context` for tags/metadata): https://docs.langchain.com/oss/python/langgraph/observability
- Time travel (`get_state_history`, replay from a checkpoint): https://docs.langchain.com/oss/python/langgraph/use-time-travel

Note: the current docs use `InMemorySaver`; `MemorySaver` (the name in your task) is the same
class under its older name and still imports from `langgraph.checkpoint.memory`.
