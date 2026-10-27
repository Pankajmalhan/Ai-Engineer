from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.metrics import RunMetrics, thread_chars
from app.offline import ScriptedChatModel
from app.tools import search_code


def test_counts_model_calls_and_tool_calls_by_name():
    run = RunMetrics()
    model = ScriptedChatModel(responder=lambda msgs: AIMessage(content="hi"))
    model.invoke("a", config={"callbacks": [run]})
    model.invoke("b", config={"callbacks": [run]})
    search_code.invoke({"query": "session"}, config={"callbacks": [run]})
    assert run.metrics.llm_calls == 2
    assert run.metrics.tool_calls == {"search_code": 1}


def test_tokens_are_summed_when_reported_and_none_when_not():
    run = RunMetrics()
    usage = {"input_tokens": 10, "output_tokens": 4, "total_tokens": 14}
    ScriptedChatModel(responder=lambda m: AIMessage(content="x", usage_metadata=usage)).invoke("q", config={"callbacks": [run]})
    ScriptedChatModel(responder=lambda m: AIMessage(content="x", usage_metadata=usage)).invoke("q", config={"callbacks": [run]})
    assert run.metrics.total_tokens == 28

    silent = RunMetrics()
    ScriptedChatModel(responder=lambda m: AIMessage(content="x")).invoke("q", config={"callbacks": [silent]})
    assert silent.metrics.total_tokens is None  # "n/a", not a misleading 0


def test_thread_chars_counts_text_and_tool_call_arguments():
    msgs = [
        HumanMessage(content="abcd"),
        AIMessage(content="", tool_calls=[{"name": "t", "args": {"q": "xy"}, "id": "1"}]),
        ToolMessage(content="123456", tool_call_id="1"),
    ]
    assert thread_chars(msgs) == 4 + len(str({"q": "xy"})) + 6


def test_finish_records_thread_size_and_time():
    run = RunMetrics()
    metrics = run.finish([HumanMessage(content="hello")])
    assert metrics.thread_chars == 5 and metrics.elapsed_s >= 0
