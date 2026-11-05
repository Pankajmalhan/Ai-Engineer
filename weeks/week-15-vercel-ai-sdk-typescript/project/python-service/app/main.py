"""HTTP surface of the LangGraph service.

    POST /v1/stream  -> Server-Sent Events, one JSON object per ``data:`` line:
                          {"type":"step","node":"retrieve","sources":[...]}   (a node finished)
                          {"type":"token","text":"..."}                      (a generated token)
                          {"type":"done"}  |  {"type":"error","message":"..."}
    POST /v1/ask     -> one JSON body {"answer": ..., "sources": [...]}  (for tool calls)
    GET  /healthz
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.graph import build_graph
from app.llm import build_llm

GENERATING_NODE = "generate"


class AskRequest(BaseModel):
    question: str = Field(min_length=1)


def sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def chunk_text(content: Any) -> str:
    """Providers send either a str or a list of content blocks; keep only the text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in content)
    return ""


def create_app(graph=None) -> FastAPI:
    load_dotenv()
    graph = graph or build_graph(build_llm())
    app = FastAPI(title="langgraph-stream-service")

    @app.get("/healthz")
    def healthz() -> dict:
        return {"ok": True}

    @app.post("/v1/ask")
    async def ask(req: AskRequest) -> dict:
        result = await graph.ainvoke({"question": req.question, "messages": []})
        return {"answer": chunk_text(result["messages"][-1].content), "sources": result["sources"]}

    @app.post("/v1/stream")
    async def stream(req: AskRequest) -> StreamingResponse:
        async def events() -> AsyncIterator[str]:
            try:
                async for mode, payload in graph.astream(
                    {"question": req.question, "messages": []}, stream_mode=["updates", "messages"]
                ):
                    if mode == "messages":
                        message_chunk, metadata = payload
                        if metadata.get("langgraph_node") == GENERATING_NODE:
                            text = chunk_text(message_chunk.content)
                            if text:
                                yield sse({"type": "token", "text": text})
                    else:  # "updates": {node_name: partial_state}
                        for node, update in payload.items():
                            event: dict[str, Any] = {"type": "step", "node": node}
                            if update and "sources" in update:
                                event["sources"] = update["sources"]
                            yield sse(event)
                yield sse({"type": "done"})
            except Exception as exc:  # surface failures to the client instead of a silently cut stream
                yield sse({"type": "error", "message": f"{type(exc).__name__}: {exc}"})

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app

