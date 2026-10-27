# Week 16b resources

## Given (from the roadmap)

- Primary: Deep Agents overview -- Docs by LangChain (`docs.langchain.com/oss/python/deepagents/overview`)
- Secondary: `langchain-ai/deepagents` on GitHub -- "the batteries-included agent harness"
- Tools listed for the week: deepagents, LangGraph, LangSmith, Python

## Refreshed links (from the roadmap's research note)

- Deep Agents: Open Source Agent Harness -- LangChain: https://www.langchain.com/deep-agents
- langchain-ai/deepagents -- GitHub: https://github.com/langchain-ai/deepagents

## Added by Claude

Pages the build was checked against (docs.langchain.com, via Context7):

- Subagents (the `SubAgent` spec fields, `isolated` vs `fork` mode, per-subagent `model`/`tools`): https://docs.langchain.com/oss/python/deepagents/subagents
- Context engineering (offloading at 20k tokens, summarisation near the window limit, subagent isolation): https://docs.langchain.com/oss/python/deepagents/context-engineering
- Backends (`StateBackend`, `StoreBackend`, `CompositeBackend`, `FilesystemBackend`): https://docs.langchain.com/oss/python/deepagents/backends
- Customization (`create_deep_agent` parameters, `interrupt_on`, `TodoListMiddleware`): https://docs.langchain.com/oss/python/deepagents/customization
- Built-in harness tools (the default tool list): https://docs.langchain.com/oss/python/deepagents/tools
- Going to production (backend choice; do not use `FilesystemBackend` in deployed agents): https://docs.langchain.com/oss/python/deepagents/going-to-production

Not verified to exist at these exact URLs: the first "Given" overview link was taken from the roadmap
text as written; the pages above are the ones the build actually used.
