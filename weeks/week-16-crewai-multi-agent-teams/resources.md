# Week 16 resources

## Given

- Primary: CrewAI documentation -- "Core Concepts" (docs.crewai.com)
- Secondary: CrewAI examples -- "research-and-write" example
- Verified Aug 2026: CrewAI's core framing is unchanged -- "Crews" (role-based) vs "Flows"
  (graph-based / event-driven).
  - "What Is CrewAI? Practical 2026 Guide to Crews, Flows, Production Agents" (no URL was supplied)
- Tools for the week: CrewAI, LangGraph, Vercel AI SDK, Langfuse (trace both)

## Added by Claude

Checked against the CrewAI and Langfuse docs (via Context7) and against the installed packages
(`crewai 1.15.28`, `langgraph 1.2.15`, `langfuse 5.0.1`, `openinference-instrumentation-crewai 1.1.21`):

- CrewAI repository (source of the `Agent` / `Task` / `Crew` / Flow decorators used here): https://github.com/crewAIInc/crewAI
- CrewAI examples repository (look here for the research-and-write example): https://github.com/crewAIInc/crewAI-examples
- Langfuse -- OpenInference (OpenTelemetry) integration, the route used to trace CrewAI: https://langfuse.com/docs/opentelemetry/example-arize
- Langfuse -- LangChain/LangGraph callback handler, the route used to trace the graph: https://langfuse.com/docs/get-started

Not linked because the exact deep URLs were not verified: the specific "Core Concepts" pages on
docs.crewai.com and Langfuse's dedicated CrewAI integration page. Find them from those sites and add
them here.

Note: the Vercel AI SDK appears in this week's tool list, but the comparison is Python-only. Week 15's
TypeScript layer can sit in front of either pipeline unchanged (both can be exposed over HTTP/SSE as in
Week 15); nothing in this week's code needed it.
