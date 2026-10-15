# Week 14 resources

## Given

- Primary: LangGraph documentation -- "Multi-Agent" section
- Secondary: LangGraph "Human-in-the-loop" how-to guide
- Tools listed for the week: LangGraph, Vercel AI SDK, Pydantic AI (type-safety), LiteLLM (provider abstraction), LangSmith

(No URLs were supplied. The docs moved to docs.langchain.com in 2026, so the pages below are the
current equivalents.)

## Added by Claude

Pages the build was checked against (docs.langchain.com, via Context7):

- Interrupts (`interrupt()`, `Command(resume=...)`, "node restarts from the beginning on resume"): https://docs.langchain.com/oss/python/langgraph/interrupts
- Graph API -- `Command` for combined state update + routing, and the static-edges-also-fire warning: https://docs.langchain.com/oss/python/langgraph/graph-api
- Use subgraphs -- sub-agents wrapped as tools, subgraph persistence modes: https://docs.langchain.com/oss/python/langgraph/use-subgraphs
- Thinking in LangGraph -- worked example of an LLM classifier node routing with `Command`: https://docs.langchain.com/oss/python/langgraph/thinking-in-langgraph
- `langgraph-supervisor` (library for the supervisor-with-sub-agents-as-tools shape): https://github.com/langchain-ai/langgraph-supervisor-py
- `langgraph-swarm` (the handoff shape, for contrast): https://github.com/langchain-ai/langgraph-swarm-py

Not located at a verified URL, so not linked: the specific "Multi-Agent" and "Human-in-the-loop"
pages named in the plan. Search for them under docs.langchain.com/oss/python/langgraph and
add the links here.
