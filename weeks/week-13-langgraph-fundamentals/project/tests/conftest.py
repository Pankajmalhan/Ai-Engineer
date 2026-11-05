from __future__ import annotations

import re
from typing import Any

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class RecordingFakeChat(BaseChatModel):
    """Deterministic stand-in for the real model. It records every prompt it was given
    (so tests can assert what the generate node actually sent) and answers by rule:
    'repeat'/'again' questions echo the last AI answer found in the history -- which only
    works if the history reached the model -- otherwise it quotes the first context line."""

    calls: list[list[BaseMessage]] = []

    @property
    def _llm_type(self) -> str:
        return "recording-fake"

    def _generate(self, messages: list[BaseMessage], stop=None, run_manager=None, **kwargs: Any) -> ChatResult:
        self.calls.append(list(messages))
        question = next(m.content for m in reversed(messages) if isinstance(m, HumanMessage))
        prior_ai = [m for m in messages if isinstance(m, AIMessage)]
        if re.search(r"\b(repeat|again|that number)\b", str(question).lower()):
            text = f"Earlier I said: {prior_ai[-1].content}" if prior_ai else "I don't know."
        else:
            first_ctx = str(messages[0].content).split("Context for this turn:\n", 1)[-1].splitlines()[0]
            text = f"Per docs: {first_ctx}"
        message = AIMessage(
            content=text,
            usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        )
        return ChatResult(generations=[ChatGeneration(message=message)])


@pytest.fixture
def fake_llm() -> RecordingFakeChat:
    llm = RecordingFakeChat()
    llm.calls = []
    return llm
