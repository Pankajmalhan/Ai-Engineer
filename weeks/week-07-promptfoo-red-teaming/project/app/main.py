"""FastAPI wrapper around RAGPipeline -- the actual red-teaming target this week.
Run with: uv run uvicorn app.main:app --port 8000
"""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from app.pipeline import RAGPipeline

app = FastAPI(title="Northwind RAG Support Assistant")
_pipeline = RAGPipeline()


class ChatRequest(BaseModel):
    question: str


class ChatResponse(BaseModel):
    answer: str
    retrieved_contexts: list[str]


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    result = _pipeline.answer(request.question)
    return ChatResponse(answer=result.answer, retrieved_contexts=result.retrieved_contexts)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
