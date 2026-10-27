"""The RAGAS judge client must be closed inside the event loop that used it -- otherwise
every scored case prints an 'Event loop is closed' traceback at garbage-collection time."""

import asyncio
import sys
import types

from app import metrics


def test_judge_client_is_closed_before_the_loop_ends(monkeypatch):
    state = {"closed_in_loop": None, "entered": False}

    class FakeAsyncOpenAI:
        async def __aenter__(self):
            state["entered"] = True
            return self

        async def __aexit__(self, *exc):
            state["closed_in_loop"] = asyncio.get_running_loop().is_running()

    class FakeFaithfulness:
        def __init__(self, llm):
            pass

        async def ascore(self, **kwargs):
            return types.SimpleNamespace(value=0.75)

    openai_mod = types.ModuleType("openai")
    openai_mod.AsyncOpenAI = FakeAsyncOpenAI
    llms_mod = types.ModuleType("ragas.llms")
    llms_mod.llm_factory = lambda model, client: object()
    coll_mod = types.ModuleType("ragas.metrics.collections")
    coll_mod.Faithfulness = FakeFaithfulness
    for name, mod in {
        "openai": openai_mod,
        "ragas": types.ModuleType("ragas"),
        "ragas.llms": llms_mod,
        "ragas.metrics": types.ModuleType("ragas.metrics"),
        "ragas.metrics.collections": coll_mod,
    }.items():
        monkeypatch.setitem(sys.modules, name, mod)

    score = metrics.score_faithfulness("q", "a", ["c"])

    assert score == 0.75
    assert state["entered"] and state["closed_in_loop"] is True
