"""FastAPI wrapper around RAGPipeline, instrumented with Langfuse via app.tracing.
Run with: uv run uvicorn app.main:app --port 8000

Container entrypoint for Week 9's Cloud Run deployment -- see ../Dockerfile. Binds to
$PORT (Cloud Run's convention, not a fixed 8000) via that Dockerfile's CMD, not here.
"""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from app.pipeline import RAGPipeline
from app.tracing import traced_answer

from dotenv import load_dotenv
load_dotenv()


app = FastAPI(title="Northwind RAG Support Assistant")
_pipeline = RAGPipeline()


class ChatRequest(BaseModel):
    question: str


class ChatResponse(BaseModel):
    answer: str
    retrieved_contexts: list[str]
    retrieved_doc_ids: list[str]


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    result = traced_answer(_pipeline, request.question)
    return ChatResponse(
        answer=result.answer,
        retrieved_contexts=result.retrieved_contexts,
        retrieved_doc_ids=result.retrieved_doc_ids,
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
