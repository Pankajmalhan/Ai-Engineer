"""The LangGraph backend: question -> retrieve (stub knowledge base) -> generate (streaming LLM).

The generate node is what produces tokens. LangGraph's ``stream_mode="messages"`` surfaces those
tokens while the node is still running -- that is the hook the SSE endpoint forwards.
"""

from __future__ import annotations

import re

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, MessagesState, StateGraph

from app.llm import CONTEXT_MARKER

# Stand-in knowledge base (real indexes arrive in Month 5, as in Week 14).
KNOWLEDGE: list[tuple[str, str]] = [
    ("langgraph-interrupt", "LangGraph's interrupt() pauses a run at a node and resumes with Command(resume=...) on the same thread_id; it needs a checkpointer."),
    ("langgraph-supervisor", "In the supervisor pattern a top-level node classifies the query and routes it to a specialist sub-agent with Command(goto=...)."),
    ("ai-sdk-streaming", "The Vercel AI SDK streams model output as a UI message stream: text-start, text-delta and text-end chunks sent over Server-Sent Events."),
    ("ai-sdk-tools", "In the Vercel AI SDK you define tools with a zod inputSchema and an execute function; streamText runs the tool loop until stopWhen is met."),
    ("litellm-proxy", "LiteLLM runs as an OpenAI-compatible proxy so one base URL can serve many providers, which makes it a convenient fallback route."),
]
TOP_K = 2


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def retrieve_docs(question: str, k: int = TOP_K) -> list[dict]:
    q = _tokens(question)
    scored = [(len(q & _tokens(f"{doc_id} {text}")), doc_id, text) for doc_id, text in KNOWLEDGE]
    ranked = sorted((s for s in scored if s[0] > 0), key=lambda s: (-s[0], s[1]))
    return [{"id": doc_id, "text": text} for _, doc_id, text in ranked[:k]]


class State(MessagesState):
    question: str
    sources: list[dict]


def build_graph(llm: BaseChatModel):
    def retrieve(state: State) -> dict:
        return {"sources": retrieve_docs(state["question"])}

    async def generate(state: State) -> dict:
        print(state)
        context = "\n".join(s["text"] for s in state["sources"])
        system = SystemMessage(content=f"Answer using only the context. Be concise.\n\n{CONTEXT_MARKER}{context}")
        reply = await llm.ainvoke([system, HumanMessage(content=state["question"])])
        return {"messages": [reply]}

    builder = StateGraph(State)
    builder.add_node("retrieve", retrieve)
    builder.add_node("generate", generate)
    builder.add_edge(START, "retrieve")
    builder.add_edge("retrieve", "generate")
    builder.add_edge("generate", END)
    return builder.compile()
