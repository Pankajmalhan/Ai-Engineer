"""Structural tests for the FastAPI wiring -- mocks the OpenAI call so these run without
OPENAI_API_KEY / any real API cost. The actual security behavior is exercised by
Promptfoo against a live server, not by these tests.
"""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_returns_answer_and_contexts():
    with patch("app.pipeline.generate_answer", return_value="30 days from purchase."):
        response = client.post("/chat", json={"question": "Refund window for annual plans?"})
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "30 days from purchase."
    assert isinstance(body["retrieved_contexts"], list)
    assert len(body["retrieved_contexts"]) > 0
