"""RAGAS Faithfulness, always judged by OpenAI regardless of which provider *generated*
the answer. Holding the judge fixed is what makes the cloud-vs-Ollama score comparison
meaningful: if the 3B model also graded its own output, a weak judge would inflate or
scramble the very difference this week measures.

See Week 5's app/metrics.py for why there is a collections/legacy fallback (RAGAS's
metric API has moved across versions). _score_* are module-level so tests can
monkeypatch them without `ragas` installed or an API key.
"""

from __future__ import annotations

import asyncio
import os


def judge_model() -> str:
    return os.environ.get("JUDGE_MODEL", "gpt-4o-mini")


def score_faithfulness(question: str, answer: str, contexts: list[str]) -> float:
    try:
        return asyncio.run(_score_collections(question, answer, contexts))
    except ImportError:
        return asyncio.run(_score_legacy(question, answer, contexts))


async def _score_collections(question: str, answer: str, contexts: list[str]) -> float:
    from openai import AsyncOpenAI
    from ragas.llms import llm_factory
    from ragas.metrics.collections import Faithfulness

    # `async with` closes the client's connections *inside* this event loop. Without it,
    # the client is garbage-collected after asyncio.run() has already closed the loop,
    # and httpx's cleanup raises "Event loop is closed" (noisy, though harmless).
    async with AsyncOpenAI() as client:
        llm = llm_factory(judge_model(), client=client)
        metric = Faithfulness(llm=llm)
        result = await metric.ascore(user_input=question, response=answer, retrieved_contexts=contexts)
    return float(result.value)


async def _score_legacy(question: str, answer: str, contexts: list[str]) -> float:
    from datasets import Dataset
    from ragas import evaluate
    from ragas.metrics import faithfulness

    dataset = Dataset.from_dict({"question": [question], "answer": [answer], "contexts": [contexts]})
    result = evaluate(dataset=dataset, metrics=[faithfulness])
    df = result.to_pandas()
    return float(df["faithfulness"].mean())
