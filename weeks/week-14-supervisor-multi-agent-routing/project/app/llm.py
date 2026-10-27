"""Chat model factory. Real runs use OpenAI (needs OPENAI_API_KEY); tests never call this."""

from __future__ import annotations

import os

from langchain_core.language_models import BaseChatModel

OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")


def build_llm() -> BaseChatModel:
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set (copy .env.example to .env)")
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(model=OPENAI_MODEL, temperature=0)
