"""Resolves RAGAS's Faithfulness metric against whichever API shape the installed
`ragas` version exposes -- see Week 5's app/metrics.py for why this needs a fallback at
all (RAGAS's metric API has moved more than once across versions). Only one metric this
week (Faithfulness), since the focus here is Braintrust/Langfuse wiring, not deepening
RAGAS itself -- see evals/eval_rag_quality.py for how it's used as a Braintrust scorer.

_score_collections/_score_legacy are module-level (not nested) specifically so tests
can monkeypatch them directly, without needing `ragas` installed or an OPENAI_API_KEY.
"""

from __future__ import annotations

import asyncio

from app.llm import OPENAI_MODEL


def score_faithfulness(question: str, answer: str, contexts: list[str]) -> float:
    try:
        return asyncio.run(_score_collections(question, answer, contexts))
    except ImportError:
        return asyncio.run(_score_legacy(question, answer, contexts))


async def _score_collections(question: str, answer: str, contexts: list[str]) -> float:
    from openai import AsyncOpenAI
    from ragas.llms import llm_factory
    from ragas.metrics.collections import Faithfulness

    from braintrust import wrap_openai

    llm = llm_factory(OPENAI_MODEL, client=wrap_openai(AsyncOpenAI()))
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
