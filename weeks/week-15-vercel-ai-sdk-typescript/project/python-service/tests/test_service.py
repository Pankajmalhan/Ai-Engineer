import json

import pytest
from fastapi.testclient import TestClient

from app.graph import build_graph, retrieve_docs
from app.llm import DemoStreamingChat
from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(build_graph(DemoStreamingChat(token_delay_ms=0))))


def read_events(client: TestClient, question: str) -> list[dict]:
    with client.stream("POST", "/v1/stream", json={"question": question}) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        lines = [line for line in resp.iter_lines() if line]
    assert all(line.startswith("data: ") for line in lines)
    return [json.loads(line[len("data: "):]) for line in lines]


def test_retrieval_ranks_by_overlap_and_ignores_unrelated_docs():
    top = retrieve_docs("how does interrupt resume a LangGraph run?")
    assert top[0]["id"] == "langgraph-interrupt"
    assert retrieve_docs("zzz qqq") == []


def test_stream_emits_steps_then_tokens_then_done_in_order(client):
    events = read_events(client, "How does the AI SDK stream text?")
    kinds = [e["type"] for e in events]
    assert kinds[0] == "step" and events[0]["node"] == "retrieve"
    assert kinds[-1] == "done"
    first_token = kinds.index("token")
    assert kinds.index("step") < first_token  # retrieval finishes before generation emits anything
    assert kinds.count("token") > 3  # genuinely incremental, not one big chunk
    assert events[0]["sources"][0]["id"] == "ai-sdk-streaming"


def test_streamed_tokens_concatenate_to_the_same_answer_as_ask(client):
    question = "How does the AI SDK stream text?"
    streamed = "".join(e["text"] for e in read_events(client, question) if e["type"] == "token")
    asked = client.post("/v1/ask", json={"question": question}).json()
    assert streamed == asked["answer"]
    assert asked["answer"].startswith("From the knowledge base:")
    assert asked["sources"][0]["id"] == "ai-sdk-streaming"


def test_no_matching_docs_still_answers_honestly(client):
    answer = client.post("/v1/ask", json={"question": "zzz qqq"}).json()["answer"]
    assert "couldn't find" in answer and client.post("/v1/ask", json={"question": "zzz qqq"}).json()["sources"] == []


def test_empty_question_is_rejected(client):
    assert client.post("/v1/stream", json={"question": ""}).status_code == 422


def test_failure_mid_graph_becomes_an_error_event_not_a_dropped_connection():
    class Boom:
        async def astream(self, *_a, **_k):
            raise RuntimeError("model down")
            yield  # pragma: no cover  (makes this an async generator)

    events = read_events(TestClient(create_app(Boom())), "anything")
    assert events == [{"type": "error", "message": "RuntimeError: model down"}]
