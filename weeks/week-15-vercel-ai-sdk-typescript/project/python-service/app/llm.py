"""Chat models for the service.

With OPENAI_API_KEY set, generation uses a real streaming model. Without one it falls back to
``DemoStreamingChat``, a deterministic stand-in that *streams* its answer word by word with a
small delay -- so the whole stack (LangGraph -> SSE -> TypeScript -> terminal) can be exercised
and its streaming behaviour verified with no keys or network.
"""

from __future__ import annotations

import os
import re
import time
from collections.abc import Iterator
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult

CONTEXT_MARKER = "Context:\n"


def _answer_text(messages: list[BaseMessage]) -> str:
    question = next((str(m.content) for m in reversed(messages) if isinstance(m, HumanMessage)), "")
    system = str(messages[0].content) if messages else ""
    context = system.split(CONTEXT_MARKER, 1)[-1].strip() if CONTEXT_MARKER in system else ""
    first = context.splitlines()[0] if context else ""
    if not first:
        return f"I couldn't find anything about {question!r} in the knowledge base."
    return f"From the knowledge base: {first}"


class DemoStreamingChat(BaseChatModel):
    """Answers from the first context line and streams it as word-sized chunks."""

    token_delay_ms: int = int(os.environ.get("DEMO_TOKEN_DELAY_MS", "40"))

    @property
    def _llm_type(self) -> str:
        return "demo-streaming"

    def _generate(self, messages: list[BaseMessage], stop=None, run_manager=None, **kwargs: Any) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=_answer_text(messages)))])

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        for piece in re.findall(r"\S+\s*", _answer_text(messages)):
            time.sleep(self.token_delay_ms / 1000)
            chunk = ChatGenerationChunk(message=AIMessageChunk(content=piece))
            if run_manager:
                run_manager.on_llm_new_token(piece, chunk=chunk)
            yield chunk


def build_llm() -> BaseChatModel:
    if os.environ.get("OPENAI_API_KEY"):
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"), temperature=0, streaming=True)
    return DemoStreamingChat()
