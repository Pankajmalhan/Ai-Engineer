"""FastAPI wrapper around RAGPipeline. Run with: uv run uvicorn app.main:app --port 8000

Which LLM answers is decided by LLM_PROVIDER (openai | ollama) -- see app/llm.py and
.env.example. The response reports the provider/model that actually served it, so a
curl against a running instance tells you which backend you are looking at.
"""

from __future__ import annotations

from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel

load_dotenv()

from app.llm import load_config  # noqa: E402  (must run after load_dotenv)
from app.pipeline import RAGPipeline  # noqa: E402

app = FastAPI(title="Northwind RAG Support Assistant (edge-capable)")
_pipeline = RAGPipeline(llm_config=load_config())


class ChatRequest(BaseModel):
    question: str


class ChatResponse(BaseModel):
    answer: str
    provider: str
    model: str
    retrieved_contexts: list[str]
    retrieved_doc_ids: list[str]


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    result = _pipeline.answer(request.question)
    print("Provider: ", _pipeline.llm_config.provider)
    print("Model: ", _pipeline.llm_config.model)
    return ChatResponse(
        answer=result.answer,
        provider=_pipeline.llm_config.provider,
        model=_pipeline.llm_config.model,
        retrieved_contexts=result.retrieved_contexts,
        retrieved_doc_ids=result.retrieved_doc_ids,
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "provider": _pipeline.llm_config.provider,
        "model": _pipeline.llm_config.model,
    }
